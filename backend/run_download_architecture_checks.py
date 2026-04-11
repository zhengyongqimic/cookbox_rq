import os

from app import (
    build_yt_dlp_options,
    get_cookie_source,
    map_download_error,
    normalize_source,
    resolve_provider_chain,
)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(condition, label):
    if not condition:
        raise AssertionError(label)


def provider_names(platform, mode="auto"):
    return [provider.__name__ for provider in resolve_provider_chain(platform, mode)]


def main():
    os.environ.setdefault(
        "DOWNLOAD_COOKIES_FILE",
        os.path.abspath(os.path.join("instance", "xiaohongshu.cookies.txt")),
    )

    assert_equal(provider_names("bilibili"), ["yt_dlp_provider"], "Bilibili provider chain")
    assert_equal(
        provider_names("xiaohongshu"),
        ["browser_session_provider", "managed_api_provider"],
        "Xiaohongshu provider chain",
    )
    assert_equal(
        provider_names("douyin"),
        ["browser_session_provider", "managed_api_provider"],
        "Douyin provider chain",
    )

    assert_equal(get_cookie_source(platform="bilibili"), ("none", None), "Bilibili cookie source")
    xhs_cookie_mode, xhs_cookie_path = get_cookie_source(platform="xiaohongshu")
    assert_equal(xhs_cookie_mode, "cookies_file", "Xiaohongshu cookie mode")
    assert_true(xhs_cookie_path.endswith("xiaohongshu.cookies.txt"), "Xiaohongshu cookie path")

    bili = normalize_source("bilibili", "https://www.bilibili.com/video/BV1Jm42137Hc?p=1")
    assert_equal(bili["original_url"], "https://www.bilibili.com/video/BV1Jm42137Hc?p=1", "Bilibili original_url")
    assert_equal(bili["resolved_url"], "https://www.bilibili.com/video/BV1Jm42137Hc?p=1", "Bilibili resolved_url")
    assert_equal(bili["canonical_url"], "https://www.bilibili.com/video/BV1Jm42137Hc", "Bilibili canonical_url")
    assert_equal(bili["source_content_id"], "BV1Jm42137Hc", "Bilibili content id")

    xhs = normalize_source("xiaohongshu", "https://www.xiaohongshu.com/discovery/item/69d636ac0000000021010e12?xsec_token=abc")
    assert_equal(
        xhs["canonical_url"],
        "https://www.xiaohongshu.com/discovery/item/69d636ac0000000021010e12",
        "Xiaohongshu canonical_url",
    )
    assert_equal(xhs["source_content_id"], "69d636ac0000000021010e12", "Xiaohongshu content id")

    opts = build_yt_dlp_options(
        {
            "platform": "bilibili",
            "output_folder": ".",
            "file_id": "architecture-check",
        },
        "yt_dlp_provider",
        use_browser_cookies=False,
    )
    assert_equal(opts.get("proxy"), "", "Bilibili yt-dlp proxy override")
    assert_true("cookiesfrombrowser" not in opts, "Bilibili should not use cookiesfrombrowser")
    assert_true("cookiefile" not in opts, "Bilibili should not use cookiefile")

    mapped = map_download_error("bilibili", "ERROR: [BiliBili] Unable to download webpage: [Errno 11002] Lookup timed out")
    assert_equal(mapped.code, "NETWORK_RESOLUTION_FAILED", "Bilibili DNS error mapping")

    print("download architecture checks passed")


if __name__ == "__main__":
    main()
