[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$ExpectedSignerSubject = $env:EXPECTED_SIGNER_SUBJECT,
    [switch]$RequireSigned
)

$ErrorActionPreference = "Stop"
$ResolvedPath = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
$Signature = Get-AuthenticodeSignature -FilePath $ResolvedPath
$Status = [string]$Signature.Status

if ($Status -notin @("Valid", "NotSigned")) {
    throw "Authenticode verification returned status '$Status' for $ResolvedPath"
}
if ($RequireSigned -and $Status -ne "Valid") {
    throw "A signed artifact is required, but the artifact status is '$Status'"
}

$SignerSubject = ""
$TimestampPresent = $false
$SignTool = $null
if ($Status -eq "Valid") {
    if ($null -ne $Signature.SignerCertificate) {
        $SignerSubject = [string]$Signature.SignerCertificate.Subject
    }
    $TimestampPresent = $null -ne $Signature.TimeStamperCertificate
    if (-not [string]::IsNullOrWhiteSpace($ExpectedSignerSubject) -and
        $SignerSubject -ne $ExpectedSignerSubject) {
        throw (
            "Signer subject mismatch. Expected '$ExpectedSignerSubject', " +
            "received '$SignerSubject'."
        )
    }
    if ($RequireSigned -and -not $TimestampPresent) {
        throw "A valid signed artifact without an Authenticode timestamp is not accepted"
    }

    $SignTool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -ne $SignTool) {
        # Windows verification command: signtool verify /pa /v <artifact>
        & $SignTool.Source verify /pa /v $ResolvedPath | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "signtool verification failed with exit code $LASTEXITCODE"
        }
    }
}

[pscustomobject]@{
    path = [IO.Path]::GetFileName($ResolvedPath)
    status = $Status
    signer_subject = $SignerSubject
    timestamp_present = $TimestampPresent
    signing_required = [bool]$RequireSigned
    signtool_available = $null -ne $SignTool
} | ConvertTo-Json -Compress
