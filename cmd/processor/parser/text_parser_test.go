package parser_test

import (
	"testing"

	"tech-letter/cmd/processor/parser"
	"tech-letter/cmd/processor/renderer"
)

var testPostUrls = []string{
	"https://tech.kakao.com/posts/770",
	"https://techblog.woowahan.com/22396/",
	"https://microservices.io//post/genaidevelopment/2025/09/10/allow-git-commit-considered-harmful.html",
	"https://techblog.gccompany.co.kr/%EA%B8%B0%EC%88%A0%EC%9D%84-%EA%B8%B0%ED%9A%8D%ED%95%98%EC%A7%80-%EC%95%8A%EB%8A%94-%EA%B8%B0%EC%88%A0%EA%B8%B0%ED%9A%8D%ED%8C%80-dae25aadd69b",
	"https://d2.naver.com/helloworld/3088532",
	"https://techblog.lycorp.co.jp/ko/techniques-for-improving-code-quality-23",
}

func TestParseArticleWithReadability(t *testing.T) {
	for _, url := range testPostUrls {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatal(err)
		}

		plainText, err := parser.ParseHtmlWithReadability(renderedHtml)
		if err != nil || plainText == "" {
			t.Fatalf("failed to parse article with readability: %v", err)
		}
	}
}

func TestParseArticleWithTrafilatura(t *testing.T) {
	for _, url := range testPostUrls {
		t.Logf("Processing URL: %s", url)
		renderedHtml, err := renderer.RenderHTML(url)
		if err != nil {
			t.Fatal(err)
		}

		plainText, err := parser.ParseHtmlWithTrafilatura(renderedHtml)
		if err != nil || plainText == "" {
			t.Fatalf("failed to parse article with trafilatura: %v", err)
		}
	}
}
