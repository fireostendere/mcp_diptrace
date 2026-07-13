class DipTraceMcpError(RuntimeError):
    pass


class ConfigurationError(DipTraceMcpError):
    pass


class PathAccessError(DipTraceMcpError):
    pass


class DocumentError(DipTraceMcpError):
    pass


class EditError(DipTraceMcpError):
    pass


class SessionError(DipTraceMcpError):
    pass
