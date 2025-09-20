package parser

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/chromedp/chromedp"
	"github.com/go-shiori/go-readability"
	"golang.org/x/net/html"
)

// GetHTML fetches the HTML content of a URL. (서버 랜더링이 사이트를 위한 parser)
func GetHTML(url string) (string, error) {
	resp, err := http.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	doc, err := html.Parse(resp.Body)
	if err != nil {
		return "", err
	}

	var b strings.Builder

	var f func(*html.Node)
	f = func(n *html.Node) {
		if n.Type == html.TextNode {
			text := strings.TrimSpace(n.Data)
			if text != "" {
				b.WriteString(text)
				b.WriteString("\n")
			}
		}
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			f(c)
		}
	}

	f(doc)
	return b.String(), nil

}

// GetRenderedHTML fetches the rendered HTML content of a URL. (클라이언트 랜더링이 필요한 사이트를 위한 parser)
func GetRenderedHTML(url string) (string, error) {
	ctx, cancel := chromedp.NewContext(context.Background())
	defer cancel()

	var htmlContent string
	err := chromedp.Run(ctx,
		chromedp.Navigate(url),
		chromedp.Sleep(2*time.Second), // JS 렌더링 대기
		chromedp.OuterHTML("html", &htmlContent),
	)
	if err != nil {
		return "", err
	}
	return htmlContent, nil
}

func ExtractTextFromHTMLWithReadability(htmlStr string) string {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return ""
	}

	article, err := readability.FromDocument(doc, nil)
	if err != nil {
		return ""
	}
	return article.TextContent
}

func ExtractImageFromHTMLWithReadability(htmlStr string) string {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return ""
	}

	article, err := readability.FromDocument(doc, nil)
	if err != nil {
		return ""
	}
	return article.Image
}
