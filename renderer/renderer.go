package renderer

import (
	"context"
	"time"

	"github.com/chromedp/chromedp"
)

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"

func RenderHTML(url string) (string, error) {

	opts := append(chromedp.DefaultExecAllocatorOptions[:],
		chromedp.UserAgent(USER_AGENT),
	)
	allocCtx, cancel := chromedp.NewExecAllocator(context.Background(), opts...)
	defer cancel()
	ctx, cancel := chromedp.NewContext(allocCtx)
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
