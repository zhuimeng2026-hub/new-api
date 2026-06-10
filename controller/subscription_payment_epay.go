package controller

import (
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/Calcium-Ion/go-epay/epay"
	"github.com/zhuimeng2026-hub/new-api/common"
	"github.com/zhuimeng2026-hub/new-api/model"
	"github.com/zhuimeng2026-hub/new-api/service"
	"github.com/zhuimeng2026-hub/new-api/setting/operation_setting"
	"github.com/zhuimeng2026-hub/new-api/setting/system_setting"
	"github.com/gin-gonic/gin"
	"github.com/samber/lo"
)

type SubscriptionEpayPayRequest struct {
	PlanId        int    `json:"plan_id"`
	PaymentMethod string `json:"payment_method"`
}

func SubscriptionRequestEpay(c *gin.Context) {
	var req SubscriptionEpayPayRequest
	if err := c.ShouldBindJSON(&req); err != nil || req.PlanId <= 0 {
		common.ApiErrorMsg(c, "参数错误")
		return
	}

	userId := c.GetInt("id")
	common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Entry: userId=%d, planId=%d, paymentMethod=%s", userId, req.PlanId, req.PaymentMethod))

	plan, err := model.GetSubscriptionPlanById(req.PlanId)
	if err != nil {
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] GetSubscriptionPlanById failed: planId=%d, err=%v", req.PlanId, err))
		common.ApiError(c, err)
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Plan found: planId=%d, title=%s, price=%.2f", plan.Id, plan.Title, plan.PriceAmount))

	if !plan.Enabled {
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Plan not enabled: planId=%d", plan.Id))
		common.ApiErrorMsg(c, "套餐未启用")
		return
	}
	if plan.PriceAmount < 0.01 {
		common.ApiErrorMsg(c, "套餐金额过低")
		return
	}
	if !operation_setting.ContainsPayMethod(req.PaymentMethod) {
		common.ApiErrorMsg(c, "支付方式不存在")
		return
	}

	if plan.MaxPurchasePerUser > 0 {
		count, err := model.CountUserSubscriptionsByPlan(userId, plan.Id)
		if err != nil {
			common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] CountUserSubscriptionsByPlan failed: userId=%d, planId=%d, err=%v", userId, plan.Id, err))
			common.ApiError(c, err)
			return
		}
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] MaxPurchasePerUser check: userId=%d, planId=%d, currentCount=%d, maxAllowed=%d", userId, plan.Id, count, plan.MaxPurchasePerUser))
		if count >= int64(plan.MaxPurchasePerUser) {
			common.ApiErrorMsg(c, "已达到该套餐购买上限")
			return
		}
	}

	callBackAddress := service.GetCallbackAddress()
	returnUrl, err := url.Parse(callBackAddress + "/api/subscription/epay/return")
	if err != nil {
		common.ApiErrorMsg(c, "回调地址配置错误")
		return
	}
	notifyUrl, err := url.Parse(callBackAddress + "/api/subscription/epay/notify")
	if err != nil {
		common.ApiErrorMsg(c, "回调地址配置错误")
		return
	}

	tradeNo := fmt.Sprintf("%s%d", common.GetRandomString(6), time.Now().Unix())
	tradeNo = fmt.Sprintf("SUBUSR%dNO%s", userId, tradeNo)

	client := GetEpayClient()
	if client == nil {
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] EpayClient is nil: userId=%d", userId))
		common.ApiErrorMsg(c, "当前管理员未配置支付信息")
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] EpayClient ready: userId=%d, tradeNo=%s", userId, tradeNo))

	order := &model.SubscriptionOrder{
		UserId:        userId,
		PlanId:        plan.Id,
		Money:         plan.PriceAmount,
		TradeNo:       tradeNo,
		PaymentMethod: req.PaymentMethod,
		CreateTime:    time.Now().Unix(),
		Status:        common.TopUpStatusPending,
	}
	if err := order.Insert(); err != nil {
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Order insert failed: tradeNo=%s, err=%v", tradeNo, err))
		common.ApiErrorMsg(c, "创建订单失败")
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Order inserted: tradeNo=%s, userId=%d, planId=%d, money=%.2f", tradeNo, userId, plan.Id, plan.PriceAmount))

	uri, params, err := client.Purchase(&epay.PurchaseArgs{
		Type:           req.PaymentMethod,
		ServiceTradeNo: tradeNo,
		Name:           fmt.Sprintf("SUB:%s", plan.Title),
		Money:          strconv.FormatFloat(plan.PriceAmount, 'f', 2, 64),
		Device:         epay.PC,
		NotifyUrl:      notifyUrl,
		ReturnUrl:      returnUrl,
	})
	if err != nil {
		common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Purchase failed: tradeNo=%s, err=%v", tradeNo, err))
		_ = model.ExpireSubscriptionOrder(tradeNo)
		common.ApiErrorMsg(c, "拉起支付失败")
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionRequestEpay] Purchase success: tradeNo=%s, uri=%s", tradeNo, uri))
	c.JSON(http.StatusOK, gin.H{"message": "success", "data": params, "url": uri})
}

func SubscriptionEpayNotify(c *gin.Context) {
	var params map[string]string

	common.SysLog(fmt.Sprintf("[SubscriptionEpayNotify] Entry: method=%s", c.Request.Method))

	if c.Request.Method == "POST" {
		// POST 请求：从 POST body 解析参数
		if err := c.Request.ParseForm(); err != nil {
			_, _ = c.Writer.Write([]byte("fail"))
			return
		}
		params = lo.Reduce(lo.Keys(c.Request.PostForm), func(r map[string]string, t string, i int) map[string]string {
			r[t] = c.Request.PostForm.Get(t)
			return r
		}, map[string]string{})
	} else {
		// GET 请求：从 URL Query 解析参数
		params = lo.Reduce(lo.Keys(c.Request.URL.Query()), func(r map[string]string, t string, i int) map[string]string {
			r[t] = c.Request.URL.Query().Get(t)
			return r
		}, map[string]string{})
	}

	if len(params) == 0 {
		_, _ = c.Writer.Write([]byte("fail"))
		return
	}

	client := GetEpayClient()
	if client == nil {
		_, _ = c.Writer.Write([]byte("fail"))
		return
	}
	verifyInfo, err := client.Verify(params)
	if err != nil || !verifyInfo.VerifyStatus {
		common.SysLog(fmt.Sprintf("[SubscriptionEpayNotify] Verify failed: err=%v, verifyStatus=%v", err, verifyInfo != nil && verifyInfo.VerifyStatus))
		_, _ = c.Writer.Write([]byte("fail"))
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionEpayNotify] Verify success: tradeNo=%s, tradeStatus=%s", verifyInfo.ServiceTradeNo, verifyInfo.TradeStatus))

	if verifyInfo.TradeStatus != epay.StatusTradeSuccess {
		_, _ = c.Writer.Write([]byte("fail"))
		return
	}

	LockOrder(verifyInfo.ServiceTradeNo)
	defer UnlockOrder(verifyInfo.ServiceTradeNo)

	if err := model.CompleteSubscriptionOrder(verifyInfo.ServiceTradeNo, common.GetJsonString(verifyInfo)); err != nil {
		common.SysLog(fmt.Sprintf("[SubscriptionEpayNotify] CompleteSubscriptionOrder failed: tradeNo=%s, err=%v", verifyInfo.ServiceTradeNo, err))
		_, _ = c.Writer.Write([]byte("fail"))
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionEpayNotify] CompleteSubscriptionOrder success: tradeNo=%s", verifyInfo.ServiceTradeNo))

	_, _ = c.Writer.Write([]byte("success"))
}

// SubscriptionEpayReturn handles browser return after payment.
// It verifies the payload and completes the order, then redirects to console.
func SubscriptionEpayReturn(c *gin.Context) {
	var params map[string]string

	common.SysLog(fmt.Sprintf("[SubscriptionEpayReturn] Entry: method=%s", c.Request.Method))

	if c.Request.Method == "POST" {
		// POST 请求：从 POST body 解析参数
		if err := c.Request.ParseForm(); err != nil {
			c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=fail")
			return
		}
		params = lo.Reduce(lo.Keys(c.Request.PostForm), func(r map[string]string, t string, i int) map[string]string {
			r[t] = c.Request.PostForm.Get(t)
			return r
		}, map[string]string{})
	} else {
		// GET 请求：从 URL Query 解析参数
		params = lo.Reduce(lo.Keys(c.Request.URL.Query()), func(r map[string]string, t string, i int) map[string]string {
			r[t] = c.Request.URL.Query().Get(t)
			return r
		}, map[string]string{})
	}

	if len(params) == 0 {
		c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=fail")
		return
	}

	client := GetEpayClient()
	if client == nil {
		c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=fail")
		return
	}
	verifyInfo, err := client.Verify(params)
	if err != nil || !verifyInfo.VerifyStatus {
		common.SysLog(fmt.Sprintf("[SubscriptionEpayReturn] Verify failed: err=%v, verifyStatus=%v", err, verifyInfo != nil && verifyInfo.VerifyStatus))
		c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=fail")
		return
	}
	common.SysLog(fmt.Sprintf("[SubscriptionEpayReturn] Verify success: tradeNo=%s, tradeStatus=%s", verifyInfo.ServiceTradeNo, verifyInfo.TradeStatus))

	if verifyInfo.TradeStatus == epay.StatusTradeSuccess {
		LockOrder(verifyInfo.ServiceTradeNo)
		defer UnlockOrder(verifyInfo.ServiceTradeNo)
		if err := model.CompleteSubscriptionOrder(verifyInfo.ServiceTradeNo, common.GetJsonString(verifyInfo)); err != nil {
			common.SysLog(fmt.Sprintf("[SubscriptionEpayReturn] CompleteSubscriptionOrder failed: tradeNo=%s, err=%v", verifyInfo.ServiceTradeNo, err))
			c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=fail")
			return
		}
		common.SysLog(fmt.Sprintf("[SubscriptionEpayReturn] CompleteSubscriptionOrder success: tradeNo=%s", verifyInfo.ServiceTradeNo))
		c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=success")
		return
	}
	c.Redirect(http.StatusFound, system_setting.ServerAddress+"/console/topup?pay=pending")
}
