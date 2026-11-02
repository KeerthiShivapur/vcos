def register_builtin_connectors(service: "ConnectorService") -> list[dict]:
    """Return list of builtin connector definitions for registration."""
    
    return [
        {
            "kind": "productivity",
            "provider": "google",
            "display_name": "Google Workspace",
            "description": "Google Workspace integration (Gmail, Drive, Calendar, Contacts, People)",
            "inbound_capabilities": [
                "read_people", "read_groups", "read_files", "read_calendar", "read_contacts"
            ],
            "outbound_capabilities": [
                "write_calendar", "write_files", "write_messages"
            ],
            "supported_entities": [
                "person", "group", "file", "event", "contact", "message"
            ],
            "supported_events": [
                "person.created", "person.updated", "person.deleted",
                "file.created", "file.updated", "file.deleted",
                "event.created", "event.updated", "event.deleted",
                "message.received",
            ],
            "sync_modes": ["initial", "incremental", "polling", "webhook"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 300,
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/contacts.readonly",
                "https://www.googleapis.com/auth/calendar.readonly",
                "https://www.googleapis.com/auth/drive.readonly",
            ],
            "required_config_fields": ["domain"],
            "optional_config_fields": ["admin_email", "service_account_key"],
            "category": "productivity",
            "tags": ["google", "workspace", "gmail", "drive", "calendar"],
            "documentation_url": "https://developers.google.com/workspace",
        },
        {
            "kind": "productivity",
            "provider": "microsoft",
            "display_name": "Microsoft 365",
            "description": "Microsoft 365 integration (Outlook, Teams, SharePoint, OneDrive, Entra ID)",
            "inbound_capabilities": [
                "read_people", "read_groups", "read_files", "read_calendar", "read_contacts",
                "read_messages", "read_channels"
            ],
            "outbound_capabilities": [
                "write_calendar", "write_files", "write_messages", "write_channels"
            ],
            "supported_entities": [
                "person", "group", "team", "channel", "file", "event", "contact", "message"
            ],
            "supported_events": [
                "person.created", "person.updated", "person.deleted",
                "team.created", "team.updated",
                "channel.created", "channel.updated",
                "message.received", "message.updated",
                "file.created", "file.updated",
                "event.created", "event.updated",
            ],
            "sync_modes": ["initial", "incremental", "polling", "webhook"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 300,
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "User.Read",
                "User.Read.All",
                "Group.Read.All",
                "Team.ReadBasic.All",
                "Channel.ReadBasic.All",
                "Files.Read.All",
                "Calendars.Read",
                "Mail.Read",
            ],
            "required_config_fields": ["tenant_id"],
            "optional_config_fields": ["client_id", "client_secret"],
            "category": "productivity",
            "tags": ["microsoft", "365", "outlook", "teams", "sharepoint", "entra"],
            "documentation_url": "https://learn.microsoft.com/en-us/graph/",
        },
        {
            "kind": "communication",
            "provider": "slack",
            "display_name": "Slack",
            "description": "Slack integration for channels, messages, users, and files",
            "inbound_capabilities": [
                "read_people", "read_groups", "read_channels", "read_messages", "read_files"
            ],
            "outbound_capabilities": [
                "write_messages", "write_files", "write_channels"
            ],
            "supported_entities": [
                "person", "group", "channel", "message", "file"
            ],
            "supported_events": [
                "message.received", "message.updated", "message.deleted",
                "channel.created", "channel.updated", "channel.deleted",
                "person.joined", "person.left",
                "file.shared", "file.unshared",
                "reaction.added", "reaction.removed",
            ],
            "sync_modes": ["initial", "incremental", "webhook"],
            "supports_webhooks": True,
            "supports_polling": False,
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "users:read", "users:read.email",
                "channels:read", "groups:read", "im:read", "mpim:read",
                "chat:write", "files:read", "files:write",
                "reactions:read", "team:read",
            ],
            "required_config_fields": ["workspace_id"],
            "optional_config_fields": ["bot_token", "signing_secret"],
            "category": "communication",
            "tags": ["slack", "chat", "messaging"],
            "documentation_url": "https://api.slack.com/",
        },
        {
            "kind": "communication",
            "provider": "teams",
            "display_name": "Microsoft Teams",
            "description": "Microsoft Teams integration (part of Microsoft 365)",
            "inbound_capabilities": [
                "read_people", "read_groups", "read_channels", "read_messages", "read_files"
            ],
            "outbound_capabilities": [
                "write_messages", "write_files", "write_channels"
            ],
            "supported_entities": [
                "person", "team", "channel", "message", "file"
            ],
            "supported_events": [
                "message.received", "message.updated", "message.deleted",
                "channel.created", "channel.updated",
                "person.added", "person.removed",
            ],
            "sync_modes": ["initial", "incremental", "webhook"],
            "supports_webhooks": True,
            "supports_polling": True,
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "ChannelMessage.Read.All", "ChannelMessage.Send",
                "Team.ReadBasic.All", "Channel.ReadBasic.All",
                "Files.Read.All", "User.Read.All",
            ],
            "required_config_fields": ["tenant_id"],
            "category": "communication",
            "tags": ["microsoft", "teams", "chat", "messaging"],
            "documentation_url": "https://learn.microsoft.com/en-us/microsoftteams/platform/",
        },
        {
            "kind": "code",
            "provider": "github",
            "display_name": "GitHub",
            "description": "GitHub integration for repositories, issues, pull requests, commits",
            "inbound_capabilities": [
                "read_repositories", "read_issues", "read_pull_requests", "read_commits",
                "read_people", "read_groups"
            ],
            "outbound_capabilities": [
                "write_issues", "write_pull_requests", "write_repositories"
            ],
            "supported_entities": [
                "repository", "issue", "pull_request", "commit", "person", "group"
            ],
            "supported_events": [
                "repository.created", "repository.updated",
                "issue.created", "issue.updated", "issue.closed",
                "pull_request.created", "pull_request.updated", "pull_request.closed",
                "commit.pushed", "release.published",
                "member.added", "member.removed",
            ],
            "sync_modes": ["initial", "incremental", "webhook", "polling"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 120,
            "auth_types": ["oauth2", "api_key"],
            "oauth_scopes": [
                "repo", "repo:status", "repo_deployment",
                "admin:repo_hook", "read:org", "read:user",
                "user:email", "read:packages",
            ],
            "required_config_fields": ["organization"],
            "optional_config_fields": ["app_id", "installation_id"],
            "category": "code",
            "tags": ["github", "git", "code", "ci/cd"],
            "documentation_url": "https://docs.github.com/en/rest",
        },
        {
            "kind": "code",
            "provider": "gitlab",
            "display_name": "GitLab",
            "description": "GitLab integration for repositories, issues, merge requests, pipelines",
            "inbound_capabilities": [
                "read_repositories", "read_issues", "read_pull_requests", "read_commits",
                "read_people", "read_groups"
            ],
            "outbound_capabilities": [
                "write_issues", "write_pull_requests", "write_repositories"
            ],
            "supported_entities": [
                "repository", "issue", "pull_request", "commit", "person", "group"
            ],
            "supported_events": [
                "repository.created", "repository.updated",
                "issue.created", "issue.updated", "issue.closed",
                "merge_request.created", "merge_request.updated", "merge_request.closed",
                "commit.pushed", "pipeline.created", "pipeline.updated",
                "member.added", "member.removed",
            ],
            "sync_modes": ["initial", "incremental", "webhook", "polling"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 120,
            "auth_types": ["oauth2", "api_key"],
            "oauth_scopes": [
                "read_api", "read_user", "read_repository",
                "write_repository", "admin_hook",
            ],
            "required_config_fields": ["url", "group"],
            "optional_config_fields": ["app_id", "secret"],
            "category": "code",
            "tags": ["gitlab", "git", "code", "ci/cd"],
            "documentation_url": "https://docs.gitlab.com/ee/api/",
        },
        {
            "kind": "work_management",
            "provider": "jira",
            "display_name": "Jira",
            "description": "Jira integration for projects, issues, sprints, boards",
            "inbound_capabilities": [
                "read_projects", "read_tasks", "read_issues", "read_people", "read_groups"
            ],
            "outbound_capabilities": [
                "write_issues", "write_projects", "write_tasks"
            ],
            "supported_entities": [
                "project", "task", "issue", "person", "group"
            ],
            "supported_events": [
                "issue.created", "issue.updated", "issue.deleted",
                "issue.transitioned", "issue.commented",
                "project.created", "project.updated",
                "sprint.created", "sprint.updated", "sprint.closed",
                "board.created", "board.updated",
            ],
            "sync_modes": ["initial", "incremental", "webhook", "polling"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 60,
            "auth_types": ["oauth2", "api_key", "basic"],
            "oauth_scopes": [
                "read:jira-work", "write:jira-work",
                "read:jira-user", "write:jira-user",
                "manage:jira-configuration",
            ],
            "required_config_fields": ["cloud_id", "base_url"],
            "optional_config_fields": ["project_keys"],
            "category": "work_management",
            "tags": ["jira", "atlassian", "agile", "project management"],
            "documentation_url": "https://developer.atlassian.com/cloud/jira/platform/",
        },
        {
            "kind": "crm",
            "provider": "salesforce",
            "display_name": "Salesforce",
            "description": "Salesforce CRM integration for accounts, contacts, opportunities, leads",
            "inbound_capabilities": [
                "read_customers", "read_deals", "read_organizations", "read_people"
            ],
            "outbound_capabilities": [
                "write_customers", "write_deals", "write_organizations"
            ],
            "supported_entities": [
                "customer", "deal", "organization", "person"
            ],
            "supported_events": [
                "account.created", "account.updated",
                "contact.created", "contact.updated",
                "opportunity.created", "opportunity.updated", "opportunity.closed",
                "lead.created", "lead.updated", "lead.converted",
            ],
            "sync_modes": ["initial", "incremental", "webhook", "polling"],
            "supports_webhooks": True,
            "supports_polling": True,
            "default_poll_interval_seconds": 300,
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "api", "refresh_token", "web", "full",
            ],
            "required_config_fields": ["instance_url"],
            "category": "crm",
            "tags": ["salesforce", "crm", "sales", "customer"],
            "documentation_url": "https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/",
        },
        {
            "kind": "hr",
            "provider": "workday",
            "display_name": "Workday",
            "description": "Workday HCM integration for employees, departments, compensation, time off",
            "inbound_capabilities": [
                "read_employees", "read_departments", "read_roles",
                "read_compensation", "read_time_off", "read_performance"
            ],
            "outbound_capabilities": [],
            "supported_entities": [
                "employee", "department", "role", "compensation", "time_off", "performance_review"
            ],
            "supported_events": [
                "employee.created", "employee.updated", "employee.terminated",
                "department.created", "department.updated",
                "position.created", "position.updated",
                "compensation.changed", "time_off.requested", "time_off.approved",
            ],
            "sync_modes": ["initial", "incremental", "polling"],
            "supports_webhooks": False,
            "supports_polling": True,
            "default_poll_interval_seconds": 3600,
            "auth_types": ["oauth2", "api_key"],
            "required_config_fields": ["tenant_url", "client_id"],
            "category": "hr",
            "tags": ["workday", "hr", "hcm", "payroll"],
            "documentation_url": "https://community.workday.com/",
        },
    ]