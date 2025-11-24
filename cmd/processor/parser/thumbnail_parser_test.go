package parser_test

import (
	"testing"

	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
)

var urlsIncludingThumbnail = []string{
	"https://microservices.io//post/genaidevelopment/2025/09/10/allow-git-commit-considered-harmful.html",
	"https://d2.naver.com/helloworld/3088532",
	"https://tech.kakao.com/posts/770",
	"https://techblog.woowahan.com/22396/",
	"https://techblog.gccompany.co.kr/%EA%B8%B0%EC%88%A0%EC%9D%84-%EA%B8%B0%ED%9A%8D%ED%95%98%EC%A7%80-%EC%95%8A%EB%8A%94-%EA%B8%B0%EC%88%A0%EA%B8%B0%ED%9A%8D%ED%8C%80-dae25aadd69b",
	"https://techblog.lycorp.co.jp/ko/techniques-for-improving-code-quality-23",
}

func TestParseTopImageFromHTML(t *testing.T) {
	for _, url := range urlsIncludingThumbnail {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatalf("failed to render HTML: %v", err)
		}

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
