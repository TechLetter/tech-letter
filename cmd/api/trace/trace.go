package trace

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"strconv"
	"sync/atomic"
	"time"
)

// 컨텍스트에 저장되는 키 타입은 외부에서 직접 사용하지 못하게 unexported로 둔다.
type ctxKey string

const ctxKeyTrace ctxKey = "trace_info"

// Info는 하나의 HTTP 요청에 대한 트레이싱 정보를 담는다.
// - RequestID: 요청 단위로 고유
// - spanSeq: 동일 RequestID 내에서 각 outbound 호출마다 1,2,3,... 순차 증가
type Info struct {
	RequestID string
	spanSeq   int64
}

// GenerateID는 트레이싱에 사용할 랜덤 ID를 생성한다.
func GenerateID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		// rand 실패 시에도 트레이싱이 완전히 깨지지 않도록 타임스탬프 기반 fallback 사용
		return time.Now().UTC().Format("20060102T150405.000000000")
	}
	return hex.EncodeToString(b[:])
}

// WithRequestAndSpan는 Request ID와 초기 Span 값(보통 0)을 컨텍스트에 저장한 새 컨텍스트를 반환한다.
func WithRequestAndSpan(ctx context.Context, requestID string, initialSpan int64) context.Context {
	info := &Info{RequestID: requestID, spanSeq: initialSpan}
	return context.WithValue(ctx, ctxKeyTrace, info)
}

func infoFromContext(ctx context.Context) *Info {
	if ctx == nil {
		return nil
	}
	v, _ := ctx.Value(ctxKeyTrace).(*Info)
	return v
}

// RequestIDFromContext는 컨텍스트에서 Request ID를 조회한다.
func RequestIDFromContext(ctx context.Context) string {
	info := infoFromContext(ctx)
	if info == nil {
		return ""
	}
	return info.RequestID
}

// CurrentSpanID는 컨텍스트에 저장된 현재 span 시퀀스 값을 문자열로 반환한다.
// (증가시키지 않는다.)
func CurrentSpanID(ctx context.Context) string {
	info := infoFromContext(ctx)
	if info == nil {
		return "0"
	}
	val := atomic.LoadInt64(&info.spanSeq)
	if val <= 0 {
		return "0"
	}
	return strconv.FormatInt(val, 10)
}

// NextSpanID는 동일한 RequestID 내에서 spanSeq를 1 증가시키고, (requestID, spanID 문자열)를 반환한다.
// 즉, 한 요청 안에서 마이크로서비스 호출이 여러 번 일어나면 spanID는 1,2,3,... 순차 증가한다.
func NextSpanID(ctx context.Context) (string, string) {
	info := infoFromContext(ctx)
	if info == nil {
		// 미들웨어 바깥에서 사용된 경우를 대비한 fallback
		reqID := GenerateID()
		return reqID, "1"
	}
	val := atomic.AddInt64(&info.spanSeq, 1)
	if val <= 0 {
		val = 1
	}
	return info.RequestID, strconv.FormatInt(val, 10)
}
