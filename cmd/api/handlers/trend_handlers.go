package handlers

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"tech-letter/cmd/api/services"
)

var allowedTrendPeriods = map[string]bool{
	"30d":  true,
	"90d":  true,
	"180d": true,
	"365d": true,
}

var allowedTrendIntervals = map[string]bool{
	"day":   true,
	"week":  true,
	"month": true,
}

func GetRisingTagsHandler(svc *services.TrendService) gin.HandlerFunc {
	return func(c *gin.Context) {
		period := c.DefaultQuery("period", "90d")
		if !allowedTrendPeriods[period] {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid trend period"})
			return
		}

		limit, _ := strconv.Atoi(c.DefaultQuery("limit", "5"))
		if limit < 1 || limit > 20 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "limit must be between 1 and 20"})
			return
		}

		resp, err := svc.GetRisingTags(c.Request.Context(), period, limit)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

func GetTrendSeriesHandler(svc *services.TrendService) gin.HandlerFunc {
	return func(c *gin.Context) {
		period := c.DefaultQuery("period", "90d")
		if !allowedTrendPeriods[period] {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid trend period"})
			return
		}

		interval := c.DefaultQuery("interval", "week")
		if !allowedTrendIntervals[interval] {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid trend interval"})
			return
		}

		resp, err := svc.GetSeries(
			c.Request.Context(),
			c.QueryArray("tags"),
			period,
			interval,
		)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}

func ListTrendPostsHandler(svc *services.TrendService) gin.HandlerFunc {
	return func(c *gin.Context) {
		period := c.DefaultQuery("period", "90d")
		if !allowedTrendPeriods[period] {
			c.JSON(http.StatusBadRequest, gin.H{"error": "invalid trend period"})
			return
		}

		page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
		pageSize, _ := strconv.Atoi(c.DefaultQuery("page_size", "10"))
		if page < 1 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "page must be greater than 0"})
			return
		}
		if pageSize < 1 || pageSize > 50 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "page_size must be between 1 and 50"})
			return
		}

		resp, err := svc.ListPosts(
			c.Request.Context(),
			c.QueryArray("tags"),
			period,
			page,
			pageSize,
		)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, resp)
	}
}
