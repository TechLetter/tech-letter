package parser_test

import (
	"strings"
	"testing"

	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
	"tech-letter/config"

	"github.com/go-shiori/go-readability"
	"golang.org/x/net/html"
)

// var urlsIncludingThumbnail = []string{
// 	"https://medium.com/daangn/%EC%98%A4%EB%8A%98%EB%8F%84-%EC%97%94%EC%A7%80%EB%8B%88%EC%96%B4%EA%B0%80-%EB%90%9C%EB%8B%A4%EA%B3%A0-%EB%A7%90%ED%96%88%EB%8B%A4-%EB%8B%B9%EA%B7%BC%ED%8E%98%EC%9D%B4-%EC%9D%B4%EC%9A%A9%EB%82%B4%EC%97%AD-%EA%B0%9C%ED%8E%B8%EA%B8%B0-89ca764ef5eb",
// 	"https://medium.com/musinsa-tech/ai%EC%99%80%EC%9D%98-%EC%84%B1%EA%B3%B5%EC%A0%81%EC%9D%B8-%EC%B2%AB-co-work-%EB%B0%94%EC%9D%B4%EB%B8%8C-%EC%BD%94%EB%94%A9%EC%9C%BC%EB%A1%9C-%ED%83%84%EC%83%9D%EB%90%9C-%EB%A7%9E%EC%B6%A4%ED%98%95-testcase-management-system-29tms-74062a620119",
// 	"https://microservices.io//post/genaidevelopment/2025/09/10/allow-git-commit-considered-harmful.html",
// 	"https://d2.naver.com/helloworld/3088532",
// 	"https://tech.kakao.com/posts/770",
// 	"https://techblog.woowahan.com/22396/",
// 	"https://techblog.gccompany.co.kr/%EA%B8%B0%EC%88%A0%EC%9D%84-%EA%B8%B0%ED%9A%8D%ED%95%98%EC%A7%80-%EC%95%8A%EB%8A%94-%EA%B8%B0%EC%88%A0%EA%B8%B0%ED%9A%8D%ED%8C%80-dae25aadd69b",
// 	"https://techblog.lycorp.co.jp/ko/techniques-for-improving-code-quality-23",
// }

var urlsIncludingThumbnail = []string{
	"https://medium.com/musinsa-tech/ai%EC%99%80%EC%9D%98-%EC%84%B1%EA%B3%B5%EC%A0%81%EC%9D%B8-%EC%B2%AB-co-work-%EB%B0%94%EC%9D%B4%EB%B8%8C-%EC%BD%94%EB%94%A9%EC%9C%BC%EB%A1%9C-%ED%83%84%EC%83%9D%EB%90%9C-%EB%A7%9E%EC%B6%A4%ED%98%95-testcase-management-system-29tms-74062a620119",
}

func TestParseTopImageFromHTML(t *testing.T) {

	config.InitApp()
	config.InitLogger(config.GetConfig().Aggregate.Logging)

	for _, url := range urlsIncludingThumbnail {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatalf("failed to render HTML: %v", err)
		}

		t.Log("Rendered HTML sample:", renderedHtml)

		topImage, err := parser.ParseTopImageFromHTML(renderedHtml, url)
		if err != nil {
			t.Fatalf("failed to parse top image: %v", err)
		}

		if topImage == "" {
			t.Fatalf("top image is empty")
		}

		t.Logf("Top Image: %s", topImage)
	}
}

func TestParseTopImageFromReadability(t *testing.T) {
	config.InitApp()
	config.InitLogger(config.GetConfig().Aggregate.Logging)
	for _, url := range urlsIncludingThumbnail {
		t.Logf("Processing URL: %s", url)
		htmlStr, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatalf("failed to render HTML: %v", err)
		}

		doc, err := html.Parse(strings.NewReader(htmlStr))
		if err != nil {
			t.Fatalf("failed to parse HTML: %v", err)
		}

		article, err := readability.FromDocument(doc, nil)
		if err != nil {
			t.Fatalf("failed to parse with readability: %v", err)
		}

		if article.Image == "" {
			t.Fatalf("main image is empty")
		}

		t.Logf("Main Image: %s", article.Image)
	}
}
