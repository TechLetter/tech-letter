package auth

import (
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func TestNewJWTManagerFromEnvRequiresSecret(t *testing.T) {
	t.Setenv("JWT_SECRET", "")
	t.Setenv("JWT_ISSUER", "issuer-for-test")

	manager, err := NewJWTManagerFromEnv()
	if err == nil {
		t.Fatalf("expected error when JWT_SECRET is empty")
	}
	if manager != nil {
		t.Fatalf("expected nil manager when env is invalid")
	}
}

func TestNewJWTManagerFromEnvUsesDefaultIssuer(t *testing.T) {
	t.Setenv("JWT_SECRET", "test-secret")
	t.Setenv("JWT_ISSUER", "")

	manager, err := NewJWTManagerFromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if manager.issuer != "tech-letter" {
		t.Fatalf("expected default issuer tech-letter, got %q", manager.issuer)
	}
	if manager.ttl != 24*time.Hour {
		t.Fatalf("expected default ttl 24h, got %s", manager.ttl)
	}
}

func TestJWTManagerSignAndParseRoundTrip(t *testing.T) {
	t.Setenv("JWT_SECRET", "test-secret")
	t.Setenv("JWT_ISSUER", "test-issuer")

	manager, err := NewJWTManagerFromEnv()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	token, err := manager.Sign("user-001", RoleAdmin)
	if err != nil {
		t.Fatalf("unexpected sign error: %v", err)
	}

	userCode, role, err := manager.Parse(token)
	if err != nil {
		t.Fatalf("unexpected parse error: %v", err)
	}
	if userCode != "user-001" {
		t.Fatalf("expected userCode user-001, got %q", userCode)
	}
	if role != RoleAdmin {
		t.Fatalf("expected role %q, got %q", RoleAdmin, role)
	}
}

func TestJWTManagerParseRejectsInvalidSignature(t *testing.T) {
	manager := &JWTManager{
		secret: []byte("service-secret"),
		issuer: "issuer",
		ttl:    time.Hour,
	}

	forgedClaims := jwt.MapClaims{
		"sub":  "user-001",
		"role": RoleUser,
		"iss":  "issuer",
		"exp":  time.Now().Add(time.Hour).Unix(),
	}
	forgedToken := jwt.NewWithClaims(jwt.SigningMethodHS256, forgedClaims)
	tokenString, err := forgedToken.SignedString([]byte("other-secret"))
	if err != nil {
		t.Fatalf("failed to sign forged token: %v", err)
	}

	_, _, err = manager.Parse(tokenString)
	if err == nil {
		t.Fatalf("expected parse error for invalid signature")
	}
}

func TestJWTManagerParseRejectsMissingSubClaim(t *testing.T) {
	manager := &JWTManager{
		secret: []byte("service-secret"),
		issuer: "issuer",
		ttl:    time.Hour,
	}

	claims := jwt.MapClaims{
		"role": RoleUser,
		"iss":  "issuer",
		"exp":  time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString(manager.secret)
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	_, _, err = manager.Parse(tokenString)
	if err == nil {
		t.Fatalf("expected parse error for missing sub claim")
	}
	if !strings.Contains(err.Error(), "token missing sub claim") {
		t.Fatalf("expected missing sub error, got %v", err)
	}
}

func TestJWTManagerParseAllowsMissingRoleClaimAsEmptyString(t *testing.T) {
	manager := &JWTManager{
		secret: []byte("service-secret"),
		issuer: "issuer",
		ttl:    time.Hour,
	}

	claims := jwt.MapClaims{
		"sub": "user-001",
		"iss": "issuer",
		"exp": time.Now().Add(time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenString, err := token.SignedString(manager.secret)
	if err != nil {
		t.Fatalf("failed to sign token: %v", err)
	}

	userCode, role, err := manager.Parse(tokenString)
	if err != nil {
		t.Fatalf("unexpected parse error: %v", err)
	}
	if userCode != "user-001" {
		t.Fatalf("expected userCode user-001, got %q", userCode)
	}
	if role != "" {
		t.Fatalf("expected empty role when claim is missing, got %q", role)
	}
}
