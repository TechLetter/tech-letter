package dto

// UserProfileDTO는 /api/v1/users/profile 응답 스키마를 나타낸다.
type UserProfileDTO struct {
	UserCode     string `json:"user_code" example:"user_1234"`
	Provider     string `json:"provider" example:"google"`
	ProviderSub  string `json:"provider_sub" example:"1234567890"`
	Email        string `json:"email" example:"user@example.com"`
	Name         string `json:"name" example:"홍길동"`
	ProfileImage string `json:"profile_image" example:"https://example.com/avatar.png"`
	Role         string `json:"role" example:"user"`
	CreatedAt    string `json:"created_at" example:"2025-01-01T12:00:00Z"`
	UpdatedAt    string `json:"updated_at" example:"2025-01-01T12:00:00Z"`
	Credits      int    `json:"credits" example:"10"`
}
