package logger

import (
	"os"
	"strings"

	"github.com/gookit/slog"
	"github.com/gookit/slog/handler"
)

// Logger 는 애플리케이션 전역에서 사용하는 최소 로거 인터페이스다.
// 필요 시 다른 구현으로 교체할 수 있도록 인터페이스로 노출한다.
type Logger interface {
	Debug(args ...any)
	Info(args ...any)
	Warn(args ...any)
	Error(args ...any)
	Debugf(format string, args ...any)
	Infof(format string, args ...any)
	Warnf(format string, args ...any)
	Errorf(format string, args ...any)
}

// Fields 는 구조화 로그를 위한 공통 필드 타입이다.
type Fields map[string]any

// Log 는 전역 로거 인스턴스다.
// InitFromEnv 가 호출되지 않더라도 기본 info 레벨로 동작하도록 초기화한다.
var Log Logger = NewLogger("info")

// InitFromEnv 는 주어진 환경변수 키에서 로그 레벨을 읽어 전역 로거를 초기화한다.
// 값이 비어 있거나 지원하지 않는 경우 기본값으로 info 를 사용한다.
func InitFromEnv(envKey string) {
	level := strings.ToLower(os.Getenv(envKey))
	if level == "" {
		level = "info"
	}
	Log = NewLogger(level)
}

// NewLogger 는 주어진 레벨로 gookit/slog 기반 로거를 생성한다.
func NewLogger(level string) Logger {
	logLevel := slog.LevelByName(level)

	var levels slog.Levels
	for _, lv := range slog.AllLevels {
		if lv <= logLevel {
			levels = append(levels, lv)
		}
	}

	h := handler.NewConsoleHandler(levels)
	// Python 쪽 로그 포맷과 최대한 유사하게 맞추기 위해,
	// 기본 필드를 datetime/level/message 로만 제한하고 나머지 정보는
	// Fields(top-level 키)로만 출력한다.
	formatter := slog.NewJSONFormatter(func(f *slog.JSONFormatter) {
		f.Fields = []string{
			slog.FieldKeyDatetime,
			slog.FieldKeyLevel,
			slog.FieldKeyMessage,
		}
		f.Aliases = slog.StringMap{
			slog.FieldKeyDatetime: "datetime",
			slog.FieldKeyLevel:    "level",
			slog.FieldKeyMessage:  "message",
		}
		// Python JsonFormatter 와 비슷한 ISO8601 형태로 맞춘다.
		f.TimeFormat = "2006-01-02T15:04:05"
	})
	h.SetFormatter(formatter)

	logger := slog.NewWithHandlers(h)
	return logger
}

// withServiceName 은 service_name 필드를 SERVICE_NAME 환경변수 기준으로 보강한다.
func withServiceName(fields Fields) Fields {
	if fields == nil {
		fields = Fields{}
	}
	if _, ok := fields["service_name"]; !ok {
		if sn := os.Getenv("SERVICE_NAME"); sn != "" {
			fields["service_name"] = sn
		}
	}
	return fields
}

// InfoWithFields 는 request_id, span_id, service_name 등 구조화 필드를 포함한
// JSON 로그를 출력하기 위한 헬퍼 함수다.
func InfoWithFields(msg string, fields Fields) {
	fields = withServiceName(fields)
	if lg, ok := Log.(*slog.Logger); ok {
		lg.WithFields(slog.M(fields)).Info(msg)
		return
	}
	Log.Info(msg)
}

func DebugWithFields(msg string, fields Fields) {
	fields = withServiceName(fields)
	if lg, ok := Log.(*slog.Logger); ok {
		lg.WithFields(slog.M(fields)).Debug(msg)
		return
	}
	Log.Debug(msg)
}

func ErrorWithFields(msg string, fields Fields) {
	fields = withServiceName(fields)
	if lg, ok := Log.(*slog.Logger); ok {
		lg.WithFields(slog.M(fields)).Error(msg)
		return
	}
	Log.Error(msg)
}
