# Maintainer Highlighting Feature

This feature marks authors and reviewers who are maintainers of the modified paths with a large dot (●) after their names in the UI.

## How it Works

1. **Parses patch diffs** to extract modified file paths
2. **Loads MAINTAINERS file** (kernel-style format with M:, R:, F: tags)
3. **Automatically reloads once per day** to stay up-to-date with mainline changes
4. **Matches paths** using the same logic as `get_maintainer.pl`
5. **Marks maintainers** with a large dot (●) suffix after their name

## Configuration

Add this section to your `config.yaml`:

```yaml
# Maintainers configuration
maintainers:
  enabled: true
  # Option 1: Load from local file
  file: /path/to/linux/MAINTAINERS

  # Option 2: Load from URL (comment out 'file' if using URL)
  # url: https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/MAINTAINERS

# Patchwork configuration (user-agent used for HTTP requests)
patchwork:
  url: https://patchwork.kernel.org/api
  project: netdev
  user_agent: "Suie/1.0 (your-email@example.com)"
```

## Automatic Reload

The MAINTAINERS file is automatically reloaded:
- **Once per day (every 24 hours)** from the last load time
- **During each poll cycle** (checks if 24 hours have passed)
- **Uses the same user_agent** as configured for Patchwork when loading from URL

This ensures your maintainer information stays current with the upstream kernel without manual intervention.

## Example Output

### Before:
```
John Doe
Jane Smith
Bob Wilson
```

### After (if John and Bob are maintainers):
```
John Doe ●
Jane Smith
Bob Wilson ●
```

## Implementation Details

### MAINTAINERS Parsing

The code uses the same logic as NIPA's maintainers parser:

- **M:** tags → Maintainers
- **R:** tags → Reviewers
- **F:** tags → File patterns (supports wildcards with `fnmatch`)

### Path Matching

Supports both:
- **Prefix matching**: `drivers/net/` matches `drivers/net/ethernet/intel/ice/ice_main.c`
- **Wildcard matching**: `drivers/net/ethernet/intel/*` matches all Intel driver files

### Email Matching

- Matches by email address (not name) since people may use different names
- Uses canonical email from `DeveloperDatabase` for proper deduplication
- Handles email aliases with `+` addressing (strips the `+alias` part)

## Performance

- MAINTAINERS file is loaded once at startup
- Automatically reloaded every 24 hours (checked during poll cycles)
- Path parsing is done once per series (cached during UI generation)
- Maintainer lookups are efficient using prefix and wildcard indexes

## Logging

When enabled, you'll see logs like:

```
INFO - Loading MAINTAINERS from file: /path/to/linux/MAINTAINERS
INFO - Loaded 500 MAINTAINERS entries
```

When reloading (every 24 hours):

```
INFO - MAINTAINERS file is 24.3 hours old, reloading...
INFO - Loading MAINTAINERS from URL: https://git.kernel.org/.../MAINTAINERS
INFO - Loaded 502 MAINTAINERS entries
```

If loading fails, the feature is disabled gracefully:

```
WARNING - Failed to load MAINTAINERS: [Error message]
```
