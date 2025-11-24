package parser

import (
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"tech-letter/config"
	"time"

	"github.com/go-shiori/go-readability"
	"golang.org/x/net/html"
)

func ParseTopImageFromHTML(htmlStr string, pageURL string) (string, error) {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return "", err
	}

	var baseURL *url.URL
	if pageURL != "" {
		if u, err := url.Parse(pageURL); err == nil {
			baseURL = u
		}
	}

	if imgURL := findTopImageWithReadability(doc, baseURL); imgURL != "" {
		return resolveImageURL(imgURL, baseURL), nil
	}

	if imgURL := findTopImageFromMeta(doc); imgURL != "" {
		return resolveImageURL(imgURL, baseURL), nil
	}

	if imgURL := findTopImageFromLink(doc); imgURL != "" {
		return resolveImageURL(imgURL, baseURL), nil
	}

	if imgURL := findTopImageFromImg(doc, baseURL, 300, 300); imgURL != "" {
		return imgURL, nil
	}

	config.Logger.Infof("there is no top image (rendered html: %d chars)", len(htmlStr))

	return "", nil
}

func findTopImageWithReadability(doc *html.Node, baseURL *url.URL) string {
	if doc == nil {
		return ""
	}

	article, err := readability.FromDocument(doc, baseURL)
	if err != nil {
		return ""
	}

	if article.Image == "" {
		return ""
	}

	return article.Image
}

func findTopImageFromMeta(doc *html.Node) string {
	// 우선순위: Open Graph 이미지 → Twitter 카드 이미지 → 기타 이미지 관련 메타
	if url := findMetaContent(doc, "property", []string{
		"og:image",
		"og:image:url",
		"og:image:secure_url",
	}); url != "" {
		return url
	}

	if url := findMetaContent(doc, "name", []string{
		"twitter:image",
		"twitter:image:src",
		"thumbnail",
		"image",
	}); url != "" {
		return url
	}

	if url := findMetaContent(doc, "itemprop", []string{
		"image",
	}); url != "" {
		return url
	}

	return ""
}

func findMetaContent(root *html.Node, key string, candidates []string) string {
	candidateSet := make(map[string]struct{}, len(candidates))
	for _, c := range candidates {
		candidateSet[strings.ToLower(c)] = struct{}{}
	}

	var result string
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n == nil || result != "" {
			return
		}

		if n.Type == html.ElementNode && n.Data == "meta" {
			var attrValue string
			var content string
			for _, a := range n.Attr {
				keyLower := strings.ToLower(a.Key)
				if keyLower == strings.ToLower(key) {
					attrValue = strings.ToLower(a.Val)
				} else if keyLower == "content" {
					content = a.Val
				}
			}

			if content != "" && attrValue != "" {
				if _, ok := candidateSet[attrValue]; ok {
					result = content
					return
				}
			}
		}

		for c := n.FirstChild; c != nil && result == ""; c = c.NextSibling {
			walk(c)
		}
	}

	walk(root)
	return result
}

func findTopImageFromLink(doc *html.Node) string {
	var result string
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n == nil || result != "" {
			return
		}

		if n.Type == html.ElementNode && n.Data == "link" {
			var rel string
			var href string
			for _, a := range n.Attr {
				keyLower := strings.ToLower(a.Key)
				if keyLower == "rel" {
					rel = strings.ToLower(a.Val)
				} else if keyLower == "href" {
					href = a.Val
				}
			}

			if href != "" && (rel == "image_src" || strings.Contains(rel, "thumbnail")) {
				result = href
				return
			}
		}

		for c := n.FirstChild; c != nil && result == ""; c = c.NextSibling {
			walk(c)
		}
	}

	walk(doc)
	return result
}

func findTopImageFromImg(doc *html.Node, baseURL *url.URL, minWidth, minHeight int) string {
	// 본문 이미지 중에서 실제 사이즈가 일정 크기 이상(썸네일로 쓰기 충분한 크기)인 이미지를 찾기 위해 사용
	var result string
	var walk func(*html.Node)
	walk = func(n *html.Node) {
		if n == nil || result != "" {
			return
		}

		if n.Type == html.ElementNode && n.Data == "img" {
			var src string
			var declaredWidth, declaredHeight int
			for _, a := range n.Attr {
				keyLower := strings.ToLower(a.Key)
				switch keyLower {
				case "src":
					src = a.Val
				case "width":
					if v, err := strconv.Atoi(a.Val); err == nil {
						declaredWidth = v
					}
				case "height":
					if v, err := strconv.Atoi(a.Val); err == nil {
						declaredHeight = v
					}
				}
			}

			if src == "" {
				goto next
			}

			absURL, ok := makeAbsoluteImageURL(src, baseURL)
			if !ok {
				goto next
			}

			if declaredWidth > 0 && declaredWidth < minWidth {
				goto next
			}
			if declaredHeight > 0 && declaredHeight < minHeight {
				goto next
			}

			if declaredWidth >= minWidth && declaredHeight >= minHeight {
				result = absURL
				return
			}

			width, height, err := fetchImageDimensions(absURL)
			if err != nil {
				goto next
			}

			if width >= minWidth && height >= minHeight {
				result = absURL
				return
			}
		}

	next:
		for c := n.FirstChild; c != nil && result == ""; c = c.NextSibling {
			walk(c)
		}
	}

	walk(doc)
	return result
}

func makeAbsoluteImageURL(src string, baseURL *url.URL) (string, bool) {
	if src == "" {
		return "", false
	}

	parsed, err := url.Parse(src)
	if err != nil {
		return "", false
	}

	if parsed.IsAbs() {
		return parsed.String(), true
	}

	if baseURL == nil {
		return "", false
	}

	return baseURL.ResolveReference(parsed).String(), true
}

func resolveImageURL(src string, baseURL *url.URL) string {
	if src == "" {
		return ""
	}

	if abs, ok := makeAbsoluteImageURL(src, baseURL); ok {
		return abs
	}

	return src
}

func fetchImageDimensions(imageURL string) (int, int, error) {
	client := &http.Client{Timeout: 30 * time.Second}
	req, err := http.NewRequest(http.MethodGet, imageURL, nil)
	if err != nil {
		return 0, 0, err
	}

	resp, err := client.Do(req)
	if err != nil {
		return 0, 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, 0, fmt.Errorf("unexpected status code %d when fetching image", resp.StatusCode)
	}

	const maxImageBytes = 8 << 20
	limited := io.LimitReader(resp.Body, maxImageBytes)
	img, _, err := image.Decode(limited)
	if err != nil {
		return 0, 0, err
	}

	bounds := img.Bounds()
	return bounds.Dx(), bounds.Dy(), nil
}
