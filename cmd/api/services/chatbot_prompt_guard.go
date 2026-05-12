package services

import (
	"regexp"
	"strings"
)

type ChatbotPromptGuardResult struct {
	Blocked   bool
	ErrorCode string
}

type chatbotPromptRule struct {
	pattern *regexp.Regexp
}

var chatbotPromptBlockRules = []chatbotPromptRule{
	{pattern: regexp.MustCompile(`(?i)((your|current|internal|hidden|exact|raw|full)\s+)(system|developer)\s+(prompt|message|instruction).*(show|print|reveal|dump|expose|display)`)},
	{pattern: regexp.MustCompile(`(?i)(show|print|reveal|dump|expose|display).*((your|current|internal|hidden|exact|raw|full)\s+)(system|developer)\s+(prompt|message|instruction)`)},
	{pattern: regexp.MustCompile(`(?i)(system|developer)\s+(prompt|message|instruction).*(verbatim|raw|exact|full|contents?).*(show|print|reveal|dump|expose|display)`)},
	{pattern: regexp.MustCompile(`(?i)(ignore|forget|bypass|override).*(previous|prior|system|developer)\s+(instruction|prompt|message|rule)`)},
	{pattern: regexp.MustCompile(`(?i)(dan mode|jailbreak|prompt injection|tool call|function call).*(execute|run|call|invoke)`)},
	{pattern: regexp.MustCompile(`(?i)(api[_ -]?key|secret|credential|env(?:ironment)? variable|access token).*(show|print|reveal|dump|expose|display)`)},
	{pattern: regexp.MustCompile(`((너의|네|현재|내부|숨겨진|원문|전체|그대로)\s*)+(시스템|개발자)\s*(프롬프트|메시지|지시).*(보여|출력|공개|노출)`)},
	{pattern: regexp.MustCompile(`(보여|출력|공개|노출).*((너의|네|현재|내부|숨겨진|원문|전체|그대로)\s*)+(시스템|개발자)\s*(프롬프트|메시지|지시)`)},
	{pattern: regexp.MustCompile(`(시스템|개발자)\s*(프롬프트|메시지|지시).*(원문|전체|그대로|내용).*(보여|출력|공개|노출)`)},
	{pattern: regexp.MustCompile(`(이전|기존)\s*(지시|규칙|명령).*(무시|잊어|우회|덮어)`)},
	{pattern: regexp.MustCompile(`(다른|타)\s*(사용자|유저).*(대화|기록|정보|데이터).*(보여|조회|알려)`)},
	{pattern: regexp.MustCompile(`(환경변수|비밀|시크릿|토큰|인증정보).*(보여|출력|공개|노출|알려)`)},
}

func EvaluateChatbotPrompt(query string) ChatbotPromptGuardResult {
	normalized := strings.TrimSpace(query)
	if normalized == "" {
		return ChatbotPromptGuardResult{Blocked: true, ErrorCode: "invalid_request"}
	}

	for _, rule := range chatbotPromptBlockRules {
		if rule.pattern.MatchString(normalized) {
			return ChatbotPromptGuardResult{Blocked: true, ErrorCode: "policy_blocked"}
		}
	}

	return ChatbotPromptGuardResult{}
}
