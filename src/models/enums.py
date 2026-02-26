import enum


class CloudProvider(str, enum.Enum):
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    kubernetes = "kubernetes"
    github = "github"
    gitlab = "gitlab"
    terraform = "terraform"


class ExecutionJobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    retrying = "retrying"
    success = "success"
    failed = "failed"


class ExecutionResultStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    timeout = "timeout"


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    tenant_admin = "tenant_admin"
    tenant_user = "tenant_user"
    viewer = "viewer"
