"""Domain knowledge base for quality engineering patterns."""

from dataclasses import dataclass, field


@dataclass
class TestPattern:
    name: str
    category: str
    trigger_keywords: list[str]
    steps_template: list[str]
    expected_template: list[str]
    priority: str = "medium"
    tags: list[str] = field(default_factory=list)


# Core testing patterns applied across domains
TEST_PATTERNS: list[TestPattern] = [
    TestPattern(
        name="Happy Path Validation",
        category="functional",
        trigger_keywords=["login", "sign in", "authenticate", "register", "signup"],
        steps_template=[
            "Navigate to the application login page",
            "Enter valid credentials",
            "Click the login/submit button",
        ],
        expected_template=[
            "User is authenticated successfully",
            "User is redirected to the dashboard/home page",
        ],
        priority="high",
        tags=["authentication", "smoke"],
    ),
    TestPattern(
        name="Invalid Credentials",
        category="functional",
        trigger_keywords=["login", "sign in", "authenticate", "password"],
        steps_template=[
            "Navigate to the login page",
            "Enter invalid username or password",
            "Click the login button",
        ],
        expected_template=[
            "Authentication fails with appropriate error message",
            "User remains on the login page",
            "No session token is issued",
        ],
        priority="high",
        tags=["authentication", "negative"],
    ),
    TestPattern(
        name="CRUD Create Operation",
        category="functional",
        trigger_keywords=["create", "add", "new", "insert", "submit form"],
        steps_template=[
            "Navigate to the create/add form",
            "Fill all mandatory fields with valid data",
            "Submit the form",
        ],
        expected_template=[
            "Record is created successfully",
            "Confirmation message is displayed",
            "New record appears in the list/view",
        ],
        priority="medium",
        tags=["crud", "functional"],
    ),
    TestPattern(
        name="CRUD Update Operation",
        category="functional",
        trigger_keywords=["update", "edit", "modify", "change"],
        steps_template=[
            "Select an existing record",
            "Modify one or more fields with valid data",
            "Save the changes",
        ],
        expected_template=[
            "Record is updated successfully",
            "Updated values are persisted and displayed",
        ],
        priority="medium",
        tags=["crud", "functional"],
    ),
    TestPattern(
        name="CRUD Delete Operation",
        category="functional",
        trigger_keywords=["delete", "remove", "cancel"],
        steps_template=[
            "Select an existing record",
            "Initiate delete/remove action",
            "Confirm deletion if prompted",
        ],
        expected_template=[
            "Record is deleted successfully",
            "Record no longer appears in the list",
        ],
        priority="medium",
        tags=["crud", "functional"],
    ),
    TestPattern(
        name="Search and Filter",
        category="functional",
        trigger_keywords=["search", "filter", "find", "query", "lookup"],
        steps_template=[
            "Navigate to the search/filter interface",
            "Enter valid search criteria",
            "Execute the search",
        ],
        expected_template=[
            "Results matching criteria are displayed",
            "Irrelevant results are excluded",
        ],
        priority="medium",
        tags=["search", "functional"],
    ),
    TestPattern(
        name="Payment Transaction",
        category="functional",
        trigger_keywords=["payment", "checkout", "purchase", "pay", "billing", "cart"],
        steps_template=[
            "Add item(s) to cart",
            "Proceed to checkout",
            "Enter valid payment details",
            "Confirm the transaction",
        ],
        expected_template=[
            "Payment is processed successfully",
            "Order confirmation is displayed",
            "Transaction receipt is generated",
        ],
        priority="high",
        tags=["payment", "e2e", "critical"],
    ),
    TestPattern(
        name="API REST Endpoint",
        category="api",
        trigger_keywords=["api", "rest", "endpoint", "graphql", "grpc", "webhook"],
        steps_template=[
            "Send request with valid payload and headers",
            "Verify response status code",
            "Validate response body schema and values",
        ],
        expected_template=[
            "API returns expected status code (200/201)",
            "Response body matches the defined schema",
        ],
        priority="high",
        tags=["api", "integration"],
    ),
    TestPattern(
        name="Authorization Check",
        category="security",
        trigger_keywords=["role", "permission", "authorize", "access control", "rbac", "admin"],
        steps_template=[
            "Authenticate as a user with restricted permissions",
            "Attempt to access a restricted resource or action",
        ],
        expected_template=[
            "Access is denied with 403 Forbidden or equivalent",
            "No unauthorized data is exposed",
        ],
        priority="high",
        tags=["security", "authorization"],
    ),
    TestPattern(
        name="Input Validation",
        category="security",
        trigger_keywords=["input", "form", "field", "validate", "submit"],
        steps_template=[
            "Enter malicious or boundary-value input (SQL injection, XSS payload, empty, max length)",
            "Submit the form or trigger validation",
        ],
        expected_template=[
            "Input is rejected or sanitized",
            "Appropriate validation error is shown",
            "No security vulnerability is exploited",
        ],
        priority="high",
        tags=["security", "validation", "negative"],
    ),
    TestPattern(
        name="Performance Load",
        category="performance",
        trigger_keywords=["performance", "load", "concurrent", "throughput", "latency", "sla"],
        steps_template=[
            "Configure load profile with target virtual users",
            "Execute load test against the target endpoint/flow",
            "Monitor response times and error rates",
        ],
        expected_template=[
            "95th percentile response time meets SLA",
            "Error rate remains below threshold",
            "System remains stable under load",
        ],
        priority="medium",
        tags=["performance", "load"],
    ),
    TestPattern(
        name="Session Management",
        category="functional",
        trigger_keywords=["session", "logout", "timeout", "token", "cookie"],
        steps_template=[
            "Authenticate and establish a session",
            "Perform logout or wait for session timeout",
            "Attempt to access a protected resource",
        ],
        expected_template=[
            "Session is terminated",
            "User is redirected to login",
            "Protected resources are inaccessible",
        ],
        priority="high",
        tags=["session", "security"],
    ),
    TestPattern(
        name="File Upload",
        category="functional",
        trigger_keywords=["upload", "file", "attachment", "document", "import"],
        steps_template=[
            "Navigate to the upload interface",
            "Select a valid file within allowed type and size limits",
            "Submit the upload",
        ],
        expected_template=[
            "File uploads successfully",
            "File is accessible or processed as expected",
        ],
        priority="medium",
        tags=["upload", "functional"],
    ),
    TestPattern(
        name="Pagination",
        category="functional",
        trigger_keywords=["pagination", "page", "list", "table", "grid", "records"],
        steps_template=[
            "Navigate to a paginated list with more records than page size",
            "Navigate to next/previous pages",
            "Change page size if supported",
        ],
        expected_template=[
            "Correct subset of records is displayed per page",
            "Navigation controls work correctly",
            "Total count is accurate",
        ],
        priority="low",
        tags=["pagination", "ui"],
    ),
]

# Merge extended patterns (mobile, accessibility, SSO, GraphQL, etc.)
from app.intelligence.patterns_extended import EXTENDED_PATTERNS  # noqa: E402

TEST_PATTERNS.extend(EXTENDED_PATTERNS)

HIGH_RISK_KEYWORDS = [
    "payment", "security", "authentication", "password", "pci", "hipaa",
    "personal data", "pii", "financial", "transaction", "admin", "production",
]

SECURITY_KEYWORDS = [
    "auth", "login", "password", "token", "encrypt", "ssl", "permission",
    "role", "injection", "xss", "csrf", "oauth", "sso",
]

PERFORMANCE_KEYWORDS = [
    "performance", "load", "concurrent", "throughput", "latency", "scale",
    "response time", "sla", "benchmark",
]
