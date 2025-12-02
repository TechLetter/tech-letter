package eventbus

import (
    "strconv"
    "strings"
    "time"
)

// ParseRetryDelayFromTopicName는 토픽 이름에서 재시도 지연 시간을 추출합니다.
// 지원 형식(단일): "<base>.retry.<n>"  (n은 1부터 시작) => RetryDelays[n-1]
// 반환: (delay, ok)
func ParseRetryDelayFromTopicName(name string) (time.Duration, bool) {
    idx := strings.LastIndex(name, ".retry.")
    if idx == -1 || idx+7 >= len(name) {
        return 0, false
    }
    suffix := name[idx+7:]
    n, err := strconv.Atoi(suffix)
    if err != nil {
        return 0, false
    }
    if n <= 0 || n > len(RetryDelays) {
        return 0, false
    }
    return RetryDelays[n-1], true
}
