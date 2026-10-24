"""Small, streaming M3U reader compatible with Python 2.7 on the receiver."""


def read_page(path, page, page_size=200):
    if page < 0 or page_size < 1:
        raise ValueError("Invalid page")

    first = page * page_size
    channels = []
    seen = 0
    pending_title = None

    with open(path, "rb") as handle:
        for raw_line in handle:
            line = raw_line.decode("utf-8", "replace").strip()
            if line.startswith("#EXTINF:"):
                pending_title = line.rsplit(",", 1)[-1].strip()
                continue
            if not line or line.startswith("#"):
                continue
            if not line.startswith(("http://", "https://")):
                pending_title = None
                continue

            if seen >= first + page_size:
                return channels, True
            if seen >= first:
                channels.append((pending_title or line, line))
            seen += 1
            pending_title = None

    return channels, False
