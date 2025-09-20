package parser_test

import (
	"fmt"
	"os"
	"tech-letter/parser"
	"testing"
	"time"
)

var testPostUrls = []string{
	"https://tech.kakao.com/posts/721",          // 카카오 MySQL InnoDB Log에 대한 이해 - (1) - tech.kakao.com
	"https://tech.kakaopay.com/post/pink-ward/", // 카카오 페이 Pink Ward - tech.kakaopay.com
	"https://d2.naver.com/helloworld/5215257",   // 네이버 오브젝트 스토리지를 활용하는 HDFS 호환 분산 파일 시스템 - d2.naver.com
}

func TestParsingTextPipeline(t *testing.T) {
	for _, url := range testPostUrls {
		now := time.Now()
		renderedHtml, err := parser.GetRenderedHTML(url)
		if err != nil {
			t.Fatal(err)
		}

		beforeFile, err := os.Create(fmt.Sprintf("before-%s.txt", time.Now().Format("2006-01-02-15-04-05")))
		if err != nil {
			t.Fatal(err)
		}
		defer beforeFile.Close()
		beforeFile.WriteString(renderedHtml)

		text := parser.ExtractTextFromHTMLWithReadability(renderedHtml)

		afterFile, err := os.Create(fmt.Sprintf("after-%s.txt", time.Now().Format("2006-01-02-15-04-05")))
		if err != nil {
			t.Fatal(err)
		}
		defer afterFile.Close()
		afterFile.WriteString(text)

		t.Log(url, time.Since(now))

	}
}

func TestParsingTopImagePipeline(t *testing.T) {
	for _, url := range testPostUrls {
		html, err := parser.GetRenderedHTML(url)
		if err != nil {
			t.Fatal(err)
		}

		image := parser.ExtractImageFromHTMLWithReadability(html)
		if image == "" {
			t.Fatal(err)
		}
		t.Log(url, image)
	}
}
