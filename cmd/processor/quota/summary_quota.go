package quota

import (
	"context"
	"sync"
	"time"

	"tech-letter/config"
)

// SummaryQuotaLimiter 는 요약용 LLM 호출에 대한 분당/일일 한도를 관리한다.
// Processor 인스턴스가 하나라는 전제를 두고 인메모리로 동작하며,
// 애플리케이션이 재시작되면 카운터가 초기화된다.
// (실제 운영에서는 영속 스토리지 기반으로 확장할 수 있도록 설계 여지를 남긴다.)
type SummaryQuotaLimiter struct {
	mu sync.Mutex

	dailyLimit int
	usedToday  int
	dayKey     string

	interval time.Duration
	lastCall time.Time
}

// NewSummaryQuotaLimiterFromConfig 는 config.yaml 의 summary_quota 설정을 기반으로
// SummaryQuotaLimiter 를 생성한다. 설정 값이 0 이하인 경우에는 해당 방향의 제한을 두지 않는다.
func NewSummaryQuotaLimiterFromConfig(cfg config.AppConfig) *SummaryQuotaLimiter {
	q := cfg.SummaryQuota

	requestsPerDay := q.RequestsPerDay
	if requestsPerDay < 0 {
		requestsPerDay = 0
	}

	requestsPerMinute := q.RequestsPerMinute
	if requestsPerMinute < 0 {
		requestsPerMinute = 0
	}

	var interval time.Duration
	if requestsPerMinute > 0 {
		interval = time.Minute / time.Duration(requestsPerMinute)
	}

	return &SummaryQuotaLimiter{
		dailyLimit: requestsPerDay,
		interval:   interval,
	}
}

// WaitAndReserve 는 요약 호출 전에 분당/일일 한도를 적용한다.
// - 일일 한도를 초과한 경우: (false, nil) 을 반환하고 호출자는 LLM 호출을 스킵해야 한다.
// - 컨텍스트 취소 등 시스템 예외 발생 시: (false, error)를 반환하여 상위에서 재시도/중단을 판단하게 한다.
func (l *SummaryQuotaLimiter) WaitAndReserve(ctx context.Context) (bool, error) {
	for {
		l.mu.Lock()

		now := time.Now().UTC()
		todayKey := now.Format("2006-01-02")
		if l.dayKey != todayKey {
			l.dayKey = todayKey
			l.usedToday = 0
		}

		if l.dailyLimit > 0 && l.usedToday >= l.dailyLimit {
			// 일일 한도 소진: 이번 호출은 요약을 수행하지 않는다.
			l.mu.Unlock()
			return false, nil
		}

		var delay time.Duration
		if l.interval > 0 && !l.lastCall.IsZero() {
			nextAllowed := l.lastCall.Add(l.interval)
			delay = time.Until(nextAllowed)
		}

		if delay <= 0 {
			// 즉시 호출 가능
			l.usedToday++
			l.lastCall = now
			l.mu.Unlock()
			return true, nil
		}

		// 잠시 대기해야 하는 경우: 락을 풀고 대기 후 다시 루프를 반복한다.
		l.mu.Unlock()
		select {
		case <-time.After(delay):
			// 다시 루프를 돌며 상태를 재평가한다.
		case <-ctx.Done():
			return false, ctx.Err()
		}
	}
}
