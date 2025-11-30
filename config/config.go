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
	API         APIConfig         `yaml:"api"`
	RetryWorker RetryWorkerConfig `yaml:"retry_worker"`
	Kafka       KafkaConfig       `yaml:"kafka"`
}

type APIConfig struct {
	Logging LoggingConfig `yaml:"logging"`
}

type RetryWorkerConfig struct {
	Logging LoggingConfig `yaml:"logging"`
}

type LoggingConfig struct {
	Level string `yaml:"level"`
}

// KafkaConfig 는 Kafka 관련 전역 설정을 담는다.
type KafkaConfig struct {
	// MessageMaxBytes 는 프로듀서에서 허용할 최대 메시지 크기(바이트)이다.
	// 0 이하면 라이브러리 기본값을 사용한다.
	MessageMaxBytes int `yaml:"message_max_bytes"`
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
