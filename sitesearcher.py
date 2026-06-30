#!/usr/bin/env python3
"""
SiteSearcher - Website phrase search tool.
Author: Igor Brzezek
Version: 0.0.1
GitHub: https://github.com/IgorBrzezek
"""

import argparse
import sys
import re
import os
import io
from urllib.parse import urlparse, urljoin
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: 'beautifulsoup4' library is required. Install with: pip install beautifulsoup4")
    sys.exit(1)


try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

BINARY_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp', '.svg',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.7z', '.rar',
    '.exe', '.dll', '.so', '.bin', '.deb', '.rpm',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
}

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp'}


class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    WHITE = '\033[97m'
    CYAN = '\033[96m'

    @staticmethod
    def colorize(text, color_code, use_color):
        if use_color:
            return f"{color_code}{text}{Colors.RESET}"
        return text


class SiteSearcher:
    def __init__(self, args):
        self.args = args
        self.visited_urls = set()
        self.results = []
        self.total_matches = 0
        self.files_with_matches = set()
        self.pages_scanned = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SiteSearcher/0.0.1 (Python)'
        })

    def c(self, text, color_code):
        return Colors.colorize(text, color_code, self.args.color)

    def info(self, message):
        print(self.c(f"[INFO] {message}", Colors.WHITE))

    def warning(self, message):
        print(self.c(f"[WARNING] {message}", Colors.YELLOW))

    def error(self, message):
        print(self.c(f"[ERROR] {message}", Colors.RED))

    def run(self):
        if self.args.quiet:
            if not self.args.output:
                print("Error: -q/--quiet requires -w (output file)")
                sys.exit(1)
            sys.stdout = open(os.devnull, 'w')

        site = self.args.site
        if not site.startswith(('http://', 'https://')):
            site = 'https://' + site
        if site.startswith('http://'):
            self.warning(f"The site '{site}' uses unencrypted HTTP.")

        parsed = urlparse(site)
        base_domain = parsed.netloc

        if self.args.externaldomains:
            msg = ("The '-externaldomains' option is enabled. The search will follow links to "
                   "external websites and domains. This can be dangerous. Use with caution.")
            print(self.c("[!!] " + msg, Colors.RED))
            print()

        if '.php' in parsed.path.lower():
            self.info(f"The site '{site}' appears to use PHP (dynamic content generation).")

        depth = self.args.depth
        if depth == 'inf':
            depth = float('inf')
        else:
            try:
                depth = int(depth)
            except ValueError:
                self.error(f"Invalid depth value: {depth}. Using default of 1.")
                depth = 1

        self.info(f"Starting search on '{site}' with depth={self.args.depth}...")
        self.crawl(site, depth, base_domain)

        if self.args.summary:
            self.print_summary()

        if self.args.output:
            self.write_report()

        if self.args.quiet:
            sys.stdout.close()
            sys.stdout = sys.__stdout__

    def is_binary_url(self, url):
        path = urlparse(url).path.lower()
        ext = os.path.splitext(path)[1]
        return ext in BINARY_EXTENSIONS, ext

    def re_flags(self):
        return re.IGNORECASE if self.args.ignore_case else 0

    def url_matches_sitepattern(self, url):
        if not self.args.sitepattern:
            return True
        pattern = self.args.sitepattern
        negate = False
        if pattern.startswith('!'):
            negate = True
            pattern = pattern[1:]
        regex = self.phrase_to_regex(pattern)
        result = bool(re.search(regex, url, self.re_flags()))
        return not result if negate else result

    def crawl(self, url, depth, base_domain):
        if url in self.visited_urls:
            return

        self.visited_urls.add(url)

        if not self.url_matches_sitepattern(url):
            if self.args.debug:
                self.info(f"Skipping URL (sitepattern mismatch): {url}")
            return

        is_binary, ext = self.is_binary_url(url)

        if is_binary:
            if ext in IMAGE_EXTENSIONS and self.args.imgsearch:
                self.search_in_image(url)
                self.pages_scanned += 1
            elif self.args.binsearch:
                content = self.fetch_page(url)
                if content is not None:
                    self.search_in_content(content, url)
                    self.pages_scanned += 1
            else:
                if self.args.debug:
                    bin_type = "image" if ext in IMAGE_EXTENSIONS else "binary"
                    self.info(f"Skipping {bin_type} file: {url}")
            return

        content = self.fetch_page(url)
        if content is None:
            return

        self.pages_scanned += 1
        self.search_in_content(content, url)

        if depth > 1:
            links = self.extract_links(content, url)
            for link in links:
                parsed_link = urlparse(link)
                if not self.args.externaldomains and parsed_link.netloc and parsed_link.netloc != base_domain:
                    continue
                if not parsed_link.scheme or parsed_link.scheme in ('http', 'https'):
                    next_depth = depth - 1 if depth != float('inf') else depth
                    self.crawl(link, next_depth, base_domain)

    def fetch_page(self, url):
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                if self.args.debug:
                    self.info(f"Skipping non-HTML content at {url} (Content-Type: {content_type})")
                return None
            return resp.text
        except requests.exceptions.RequestException as e:
            if self.args.debug:
                self.error(f"Failed to fetch {url}: {e}")
            return None

    def extract_links(self, html_content, base_url):
        soup = BeautifulSoup(html_content, 'html.parser')
        links = set()
        for tag in soup.find_all('a', href=True):
            href = tag['href'].strip()
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url += f"?{parsed.query}"
            if clean_url.startswith(('http://', 'https://')):
                links.add(clean_url)
        return links

    def search_in_content(self, content, url):
        phrase = self.args.text
        negate = False
        if phrase.startswith('!'):
            negate = True
            phrase = phrase[1:]

        regex_pattern = self.phrase_to_regex(phrase)
        flags = self.re_flags()

        lines = content.split('\n')
        found_in_page = False

        if negate or self.args.invert:
            for line_num, line in enumerate(lines, 1):
                if not re.search(regex_pattern, line, flags):
                    matched_text = line.strip()[:80]
                    self.results.append((url, line_num, 0, matched_text))
                    self.total_matches += 1
                    self.files_with_matches.add(url)

                    result_line = f"{url}, LINE:{line_num}, COL:0 -> '{matched_text}'"
                    print(self.c(result_line, Colors.GREEN))
                    found_in_page = True
        else:
            for line_num, line in enumerate(lines, 1):
                for match in re.finditer(regex_pattern, line, flags):
                    char_pos = match.start() + 1
                    matched_text = match.group(0)
                    self.results.append((url, line_num, char_pos, matched_text))
                    self.total_matches += 1
                    self.files_with_matches.add(url)

                    result_line = f"{url}, LINE:{line_num}, COL:{char_pos} -> '{matched_text}'"
                    print(self.c(result_line, Colors.GREEN))
                    found_in_page = True

    def search_in_image(self, url):
        if not HAS_PIL or not HAS_TESSERACT:
            if self.args.debug:
                self.info(f"Cannot OCR {url}: install pytesseract and Pillow")
            return

        try:
            if self.args.debug:
                self.info(f"Attempting OCR on {url}")
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            img = PILImage.open(io.BytesIO(resp.content))
            text = pytesseract.image_to_string(img)
            if text.strip():
                self.search_in_content(text, url)
        except Exception as e:
            if self.args.debug:
                self.error(f"Failed to OCR {url}: {e}")

    def phrase_to_regex(self, phrase):
        i = 0
        regex_chars = []
        while i < len(phrase):
            c = phrase[i]
            if c == '\\' and i + 1 < len(phrase):
                next_c = phrase[i + 1]
                if next_c in ('*', '?', '"', '\\'):
                    regex_chars.append(re.escape(next_c))
                    i += 2
                    continue
            if c == '*':
                regex_chars.append('.*')
            elif c == '?':
                regex_chars.append('.')
            else:
                regex_chars.append(re.escape(c))
            i += 1

        return ''.join(regex_chars)

    def print_summary(self):
        print()
        print(self.c("=" * 50, Colors.WHITE))
        print(self.c("SUMMARY", Colors.WHITE))
        print(self.c("=" * 50, Colors.WHITE))
        print(self.c(f"Total matches found: {self.total_matches}", Colors.GREEN))
        print(self.c(f"Files/pages with matches: {len(self.files_with_matches)}", Colors.GREEN))
        print(self.c(f"Total pages scanned: {self.pages_scanned}", Colors.GREEN))

    def write_report(self):
        try:
            with open(self.args.output, 'w', encoding='utf-8') as f:
                f.write(f"SiteSearcher Report\n")
                f.write(f"Author: Igor Brzezek\n")
                f.write(f"Version: 0.0.1\n")
                f.write(f"{'=' * 50}\n")
                f.write(f"Site: {self.args.site}\n")
                f.write(f"Phrase: {self.args.text}\n")
                f.write(f"Depth: {self.args.depth}\n")
                f.write(f"{'=' * 50}\n\n")

                for url, line_num, char_pos, matched_text in self.results:
                    f.write(f"{url}, LINE:{line_num}, COL:{char_pos} -> '{matched_text}'\n")

                if self.args.summary:
                    f.write(f"\n{'=' * 50}\n")
                    f.write(f"SUMMARY\n")
                    f.write(f"{'=' * 50}\n")
                    f.write(f"Total matches: {self.total_matches}\n")
                    f.write(f"Files with matches: {len(self.files_with_matches)}\n")
                    f.write(f"Pages scanned: {self.pages_scanned}\n")

            self.info(f"Report saved to '{self.args.output}'")
        except IOError as e:
            self.error(f"Failed to write report to '{self.args.output}': {e}")


def create_parser():
    parser = argparse.ArgumentParser(
        add_help=False,
        description='SiteSearcher - A tool for searching phrases across websites.'
    )
    parser.add_argument('-site', type=str, help='Website URL to search')
    parser.add_argument('-depth', type=str, default='1', help='Search depth (default: 1, "inf" for unlimited)')
    parser.add_argument('-externaldomains', action='store_true', help='Allow searching external domains')
    parser.add_argument('--color', action='store_true', help='Enable colored output')
    parser.add_argument('-text', type=str, help='Phrase to search for (supports * and ? wildcards)')
    parser.add_argument('-w', type=str, dest='output', help='Write report to file')
    parser.add_argument('-summary', action='store_true', help='Show search summary')
    parser.add_argument('--debug', action='store_true', help='Show debug messages (skipped files, errors)')
    parser.add_argument('--binsearch', action='store_true', help='Also search inside binary files')
    parser.add_argument('--imgsearch', action='store_true', help='Also search for phrase in images (OCR)')
    parser.add_argument('--sitepattern', type=str, help='URL pattern filter (* and ? wildcards)')
    parser.add_argument('--invert', action='store_true', help='Invert text search (show non-matching lines)')
    parser.add_argument('-i', '--ignore-case', action='store_true', dest='ignore_case', help='Case-insensitive search')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress all console output (requires -w)')
    parser.add_argument('-h', action='store_true', dest='simple_help', help='Show simple help')
    parser.add_argument('--help', action='store_true', dest='detailed_help', help='Show detailed help with examples')
    return parser


def show_simple_help():
    print("SiteSearcher v0.0.1 by Igor Brzezek")
    print("GitHub: https://github.com/IgorBrzezek")
    print()
    print("Usage: python sitesearcher.py -site URL -text PHRASE [options]")
    print()
    print("Options:")
    print("  -site ADDR       Website URL to search")
    print("  -text PHRASE     Phrase to search for")
    print("  -depth N         Search depth (default: 1, 'inf' for unlimited)")
    print("  -externaldomains Allow searching external domains (dangerous)")
    print("  --color          Enable colored output")
    print("  -w FILE          Write report to file")
    print("  -summary         Show search summary")
    print("  --debug          Show debug messages")
    print("  --binsearch      Also search inside binary files")
    print("  --imgsearch      Also search for phrase in images (OCR)")
    print("  --sitepattern    URL pattern filter (*, ? wildcards)")
    print("  --invert         Invert text search (show non-matching lines)")
    print("  -i, --ignore-case Case-insensitive search")
    print("  -q, --quiet      Suppress all console output (requires -w)")
    print("  -h               Show this help")
    print("  --help           Show detailed help with examples")


def show_detailed_help():
    print("SiteSearcher v0.0.1 by Igor Brzezek")
    print("GitHub: https://github.com/IgorBrzezek")
    print()
    print("DESCRIPTION")
    print("  SiteSearcher crawls websites and searches for a given phrase in the HTML")
    print("  source code. It supports wildcard patterns and can follow links to")
    print("  specified depth.")
    print()
    print("USAGE")
    print("  python sitesearcher.py -site <URL> -text <PHRASE> [options]")
    print()
    print("OPTIONS")
    print("  -site ADDR       Target website URL to start searching from.")
    print()
    print("  -text PHRASE     Phrase to search for. Supports wildcards:")
    print("                   *  - matches any sequence of characters")
    print("                   ?  - matches any single character")
    print("                   Use \\* and \\? for literal * and ?.")
    print()
    print("  -depth N         Maximum link depth to crawl.")
    print("                   Default: 1 (search only the given page).")
    print("                   Use 'inf' for unlimited depth.")
    print("                   Example: -depth 2 searches the page and all linked pages.")
    print()
    print("  -externaldomains Allow the crawler to follow links to other domains.")
    print("                   Without this flag, only pages within the original domain")
    print("                   are searched. WARNING: This can lead to extensive crawling.")
    print()
    print("  --color          Enable colored terminal output.")
    print("                   Info in white, warnings in yellow, errors in red.")
    print()
    print("  -w FILE          Save the search results to a file.")
    print()
    print("  -summary         Display a summary of total matches and pages scanned.")
    print()
    print("  --debug          Show debug messages including skipped binary/image files")
    print("                   and fetch errors.")
    print()
    print("  --binsearch      Also follow links to binary files (PDFs, archives, etc.)")
    print("                   and search their raw content for the phrase.")
    print()
    print("  --imgsearch      Also search for the phrase inside images using OCR.")
    print("                   Requires: pip install pytesseract Pillow")
    print()
    print("  --sitepattern    Filter pages by URL pattern. Supports * and ?")
    print("                   wildcards (same as -text).")
    print()
    print("  --invert         Invert text search. Show lines that do NOT")
    print("                   contain the specified phrase.")
    print()
    print("  -i, --ignore-case Case-insensitive search for both -text and")
    print("                   --sitepattern.")
    print()
    print("  -q, --quiet      Suppress all console output. Only the report file")
    print("                   is written. Requires -w.")
    print()
    print("  -h               Show simple help.")
    print("  --help           Show this detailed help.")
    print()
    print("EXAMPLES")
    print("  Search for 'janek' on a single page:")
    print("    python sitesearcher.py -site https://example.com -text janek")
    print()
    print("  Search with wildcard, depth 2, with colors:")
    print("    python sitesearcher.py -site https://example.com -text 'j*ek' -depth 2 --color")
    print()
    print("  Search entire site with summary and report:")
    print("    python sitesearcher.py -site https://example.com -text 'foo?' -depth inf -summary -w report.txt")
    print()
    print("  Search with external domains allowed:")
    print("    python sitesearcher.py -site https://example.com -text 'hello' -externaldomains")
    print()
    print("NOTES")
    print("  - The script shows line number and character position for each match.")
    print("  - Dynamically generated pages (PHP) are flagged with an info message.")
    print("  - HTTP URLs trigger a warning.")


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.simple_help:
        show_simple_help()
        return

    if args.detailed_help:
        show_detailed_help()
        return

    if not args.site:
        print("Error: -site argument is required.")
        print("Use -h for help or --help for detailed help.")
        sys.exit(1)

    if not args.text:
        print("Error: -text argument is required.")
        print("Use -h for help or --help for detailed help.")
        sys.exit(1)

    searcher = SiteSearcher(args)
    try:
        searcher.run()
    except KeyboardInterrupt:
        print()
        print(searcher.c("[INFO] Search interrupted by user. Showing partial results...", Colors.YELLOW))
        if args.summary:
            searcher.print_summary()
        if args.output:
            searcher.write_report()
        sys.exit(0)


if __name__ == '__main__':
    main()
