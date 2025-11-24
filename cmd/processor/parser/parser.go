package parser

import (
	"log"
	"strings"

	"github.com/advancedlogic/GoOse/pkg/goose"
	"github.com/go-shiori/go-readability"
	"github.com/markusmobius/go-trafilatura"
	"golang.org/x/net/html"
)

type ParsedArticle struct {
	PlainTextContent string
	TopImage         string
}

func ParseHtmlWithReadability(htmlStr string) (*ParsedArticle, error) {
	doc, err := html.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return nil, err
	}

	article, err := readability.FromDocument(doc, nil)
	if err != nil {
		return nil, err
	}
	return &ParsedArticle{
		PlainTextContent: article.TextContent,
		TopImage:         article.Image,
	}, nil
}

func ParseHtmlWithTrafilatura(htmlStr string) (*ParsedArticle, error) {
	opts := trafilatura.Options{
		IncludeImages: true,
	}

	article, err := trafilatura.Extract(strings.NewReader(htmlStr), opts)
	if err != nil {
		return nil, err
	}

	return &ParsedArticle{
		PlainTextContent: article.ContentText,
		TopImage:         article.Metadata.Image,
	}, nil
}

func ParseHtmlWithGoose(htmlStr string) (*ParsedArticle, error) {
	g := goose.New()
	article, err := g.ExtractFromRawHTML(htmlStr, "")
	if err != nil {
		log.Fatalf("Error extracting article: %v", err)
	}
	return &ParsedArticle{
		PlainTextContent: article.CleanedText,
		TopImage:         article.TopImage,
	}, nil
}
