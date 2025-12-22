package dto

// CreditDTO는 크레딧 조회 응답 스키마를 나타낸다.
type CreditDTO struct {
	Remaining int    `json:"remaining" example:"7"`
	Granted   int    `json:"granted" example:"10"`
	ExpiredAt string `json:"expired_at" example:"2025-01-01T00:00:00Z"`
}

// ConsumeCreditsRequest는 크레딧 소비 요청 스키마를 나타낸다.
type ConsumeCreditsRequest struct {
	Amount int `json:"amount" example:"1"`
}

// ConsumeCreditsResponse는 크레딧 소비 응답 스키마를 나타낸다.
type ConsumeCreditsResponse struct {
	Remaining int    `json:"remaining" example:"9"`
	ExpiredAt string `json:"expired_at" example:"2025-01-01T00:00:00Z"`
}

// GrantCreditsRequest는 관리자 크레딧 부여 요청 스키마를 나타낸다.
type GrantCreditsRequest struct {
	Amount int    `json:"amount" example:"10"`
	Reason string `json:"reason" example:"admin_grant"`
}
