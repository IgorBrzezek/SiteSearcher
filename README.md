# SiteSearcher

Website phrase search tool. Crawls websites and searches for a given phrase in the HTML source code. Supports wildcard patterns, link depth control, and various filtering options.

**Author:** Igor Brzezek  
**Version:** 0.0.2  
**GitHub:** https://github.com/IgorBrzezek

## Requirements

- Python 3.6+
- `requests` library (>=2.28.0)
- `beautifulsoup4` library (>=4.12.0)

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional (for OCR image search):

```bash
pip install pytesseract Pillow
```

## Usage

```bash
python sitesearcher.py -site <URL> -text <PHRASE> [options]
```

### Basic example

```bash
python sitesearcher.py -site https://example.com -text "cisco"
```

URL scheme (`https://`) is optional — if omitted, `https://` is added automatically.

## Options

| Option | Description |
|--------|-------------|
| `-site ADDR` | Website URL to search |
| `-text PHRASE` | Phrase to search for (supports `*` and `?` wildcards) |
| `-depth N` | Search depth (default: 1, `inf` for unlimited) |
| `-externaldomains` | Allow searching external domains (dangerous) |
| `--color` | Enable colored terminal output |
| `-w FILE` | Write report to file |
| `-summary` | Show search summary |
| `--debug` | Show debug messages |
| `--binsearch` | Also search inside binary files |
| `--imgsearch` | Search for phrase in images (OCR, requires pytesseract) |
| `--sitepattern PATTERN` | Filter pages by URL pattern (`*` and `?` wildcards) |
| `--exclude FILES` | Exclude filenames from search (`*` and `?` wildcards, comma-separated) |
| `--invert` | Invert text search (show non-matching lines) |
| `-i`, `--ignore-case` | Case-insensitive search |
| `-q`, `--quiet` | Suppress console output (requires `-w`) |
| `-h` | Show simple help |
| `--help` | Show detailed help with examples |

## Wildcards

Both `-text` and `--sitepattern` and `--exclude` support:

- `*` — matches any sequence of characters
- `?` — matches any single character
- Use `\*` and `\?` for literal `*` and `?`

## Examples

Search for 'example' on a single page:

```bash
python sitesearcher.py -site https://example.com -text example
```

Search with wildcard, depth 2, with colors:

```bash
python sitesearcher.py -site https://example.com -text 'j*ek' -depth 2 --color
```

Search entire site with summary and report:

```bash
python sitesearcher.py -site https://example.com -text 'foo?' -depth inf -summary -w report.txt
```

Search excluding certain file types:

```bash
python sitesearcher.py -site https://example.com -text 'cisco' --exclude '*.pdf,*.zip' --debug
```

Search with external domains allowed:

```bash
python sitesearcher.py -site https://example.com -text 'hello' -externaldomains
```

## Notes

- The script shows line number and character position for each match.
- Dynamically generated pages (PHP) are flagged with an info message.
- HTTP URLs trigger a warning.
- The `--exclude` option filters by the filename component of the URL (the last part of the path).
