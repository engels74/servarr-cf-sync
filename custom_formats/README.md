# Custom Formats

This directory contains custom format definitions for Radarr and Sonarr. Use the `_template.json` file as a starting point for creating new custom formats.

## Template Structure

The `_template.json` file provides a basic structure for custom formats. Here are the essential fields:

### Basic Fields
- `name`: The name of your custom format as it will appear in Radarr/Sonarr

### cfSync Fields
- `cfSync_version`: Version number (semver) used to track updates (required)
- `cfSync_radarr`: Set to false to exclude from Radarr instances (default: true)
- `cfSync_sonarr`: Set to false to exclude from Sonarr instances (default: true)
- `cfSync_score`: Score to assign in quality profiles (default: 0)

For detailed information about other fields and specifications, please refer to the Servarr wiki:
- Radarr: https://wiki.servarr.com/en/radarr/settings#custom-formats
- Sonarr: https://wiki.servarr.com/en/sonarr/settings#custom-formats

## Example Usage

Here's an example of a custom format that blocks German DL releases. This format applies a negative score (-10000) to ensure these releases are never downloaded:

```json
{
  "name": "Block German DL Releases",
  "cfSync_version": "0.0.1",
  "cfSync_radarr": true,
  "cfSync_sonarr": true,
  "cfSync_score": -10000,
  "includeCustomFormatWhenRenaming": false,
  "specifications": [
    {
      "name": "German DL Blocker",
      "implementation": "ReleaseTitleSpecification",
      "negate": false,
      "required": false,
      "fields": {
        "value": "(?i)german(?:\\.[\\w-]+)*\\.dl\\."
      }
    }
  ]
}
```

This example demonstrates:
1. Using cfSync fields to control where the format applies (both Radarr and Sonarr)
2. Setting a negative score to block matches
3. Using a regex pattern to match release titles containing "german" and "dl"

