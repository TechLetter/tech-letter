package auth

import (
	"fmt"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const (
	RoleUser  = "user"
	RoleAdmin = "admin"
)

// JWTManager 는 HS256 단일 시크릿 문자열을 사용해 JWT 를 발급/검증한다.
type JWTManager struct {
	secret []byte
	issuer string
	ttl    time.Duration
}

// NewJWTManagerFromEnv 는 환경변수에서 시크릿/issuer 를 읽어 JWTManager 를 생성한다.
//
// - JWT_SECRET: HS256 서명에 사용할 시크릿 문자열(필수)
// - JWT_ISSUER: iss 클레임 값(선택, 기본값 "tech-letter")
func NewJWTManagerFromEnv() (*JWTManager, error) {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		return nil, fmt.Errorf("JWT_SECRET is required")
	}

	issuer := os.Getenv("JWT_ISSUER")
	if issuer == "" {
		issuer = "tech-letter"
	}

	return &JWTManager{
		secret: []byte(secret),
		issuer: issuer,
		ttl:    24 * time.Hour,
	}, nil
}

func (m *JWTManager) Sign(userCode, role string) (string, error) {
	claims := jwt.MapClaims{
		"sub":  userCode,
		"role": role,
		"iss":  m.issuer,
		"exp":  time.Now().Add(m.ttl).Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(m.secret)
}

func (m *JWTManager) Parse(tokenString string) (string, string, error) {
	parsed, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return m.secret, nil
	})
	if err != nil {
		return "", "", err
	}

	claims, ok := parsed.Claims.(jwt.MapClaims)
	if !ok || !parsed.Valid {
		return "", "", fmt.Errorf("invalid token claims")
	}

	sub, _ := claims["sub"].(string)
	role, _ := claims["role"].(string)
	if sub == "" {
		return "", "", fmt.Errorf("token missing sub claim")
	}

	return sub, role, nil
}
