package config

import (
	"os"
	"path/filepath"

	"github.com/joho/godotenv"
	"gopkg.in/yaml.v3"
)

const ENV_FILE = ".env"
const CONFIG_FILE = "config.yaml"

type AppConfig struct {
	Logging            LoggingConfig      `yaml:"logging"`
	GeminiModel        string             `yaml:"gemini_model"`
	BlogFetchBatchSize int                `yaml:"blog_fetch_batch_size"`
	Blogs              []BlogSource       `yaml:"blogs"`
	SummaryQuota       SummaryQuotaConfig `yaml:"summary_quota"`
}

type LoggingConfig struct {
	Level string `yaml:"level"`
}

// SummaryQuotaConfig 는 요약용 LLM 호출에 대한 속도/일일 한도를 정의한다.
// 애플리케이션 별로 설정을 분리할 계획이지만, 현재는 전역 설정으로 사용한다.
type SummaryQuotaConfig struct {
	// RequestsPerMinute 는 요약용 LLM 호출에 대한 분당 최대 요청 수이다.
	// 0 이하면 제한 없음으로 간주한다.
	RequestsPerMinute int `yaml:"requests_per_minute"`

	// RequestsPerDay 는 요약용 LLM 호출에 대한 일일 최대 요청 수이다.
	// 0 이하면 제한 없음으로 간주한다.
	RequestsPerDay int `yaml:"requests_per_day"`
}

// BlogSource is a single blog configuration item
type BlogSource struct {
	Name     string `yaml:"name"`
	URL      string `yaml:"url"`
	RSSURL   string `yaml:"rss_url"`
	BlogType string `yaml:"blog_type"`
}

var config *AppConfig

func InitApp() {
	// load environment variables
	godotenv.Load(filepath.Join(GetBasePath(), ENV_FILE))

	// load configuration file
	data, err := os.ReadFile(filepath.Join(GetBasePath(), CONFIG_FILE))
	if err != nil {
		panic(err)
	}

	var c AppConfig
	err = yaml.Unmarshal(data, &c)
	if err != nil {
		panic(err)
	}
	config = &c
}

func GetConfig() AppConfig {
	if config == nil {
		InitApp()
	}

	return *config
}

func GetBasePath() string {
	cwd, err := os.Getwd()
	if err != nil {
		return ""
	}

	dir := cwd
	for {
		cfgPath := filepath.Join(dir, CONFIG_FILE)
		if info, err := os.Stat(cfgPath); err == nil && !info.IsDir() {
			return dir
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}

	return ""
}
