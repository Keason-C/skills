<!-- TEMPLATE — when filling in: replace every {{...}} with real content and delete all <!-- --> comments, this line included. -->
<!-- The single API doc for the whole project: one ## section per API, appended as Phases progress. -->

# API

## {{METHOD}} {{PATH}}

Type: `{{query|command|stream}}`
Description: {{DESCRIPTION}}
Auth: {{AUTH}}
Idempotent: {{yes|no}}

Params:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `{{field}}` | `{{type}}` | {{yes/no}} | {{constraint or default}} |

Response:

```json
{{RESPONSE_EXAMPLE}}
```

Errors:

<!-- List only the errors this endpoint raises. HTTP status = category, `code` = specific cause; clients branch on `code`. -->

| HTTP | `code` | Trigger |
| --- | --- | --- |
| `{{status}}` | `{{ERROR_CODE}}` | {{TRIGGER}} |
