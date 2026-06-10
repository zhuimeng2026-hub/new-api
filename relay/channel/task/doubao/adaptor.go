package doubao

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/zhuimeng2026-hub/new-api/common"

	"github.com/zhuimeng2026-hub/new-api/constant"
	"github.com/zhuimeng2026-hub/new-api/dto"
	"github.com/zhuimeng2026-hub/new-api/model"
	"github.com/zhuimeng2026-hub/new-api/relay/channel"
	taskcommon "github.com/zhuimeng2026-hub/new-api/relay/channel/task/taskcommon"
	relaycommon "github.com/zhuimeng2026-hub/new-api/relay/common"
	"github.com/zhuimeng2026-hub/new-api/service"
	"github.com/zhuimeng2026-hub/new-api/setting/ratio_setting"

	"github.com/gin-gonic/gin"
	"github.com/pkg/errors"
)

// ============================
// Request / Response structures
// ============================

type ContentItem struct {
	Type     string          `json:"type"`                // "text", "image_url" or "video"
	Text     string          `json:"text,omitempty"`      // for text type
	ImageURL *ImageURL       `json:"image_url,omitempty"` // for image_url type
	Video    *VideoReference `json:"video,omitempty"`     // for video (sample) type
	Role     string          `json:"role,omitempty"`      // reference_image / first_frame / last_frame
}

type ImageURL struct {
	URL string `json:"url"`
}

type VideoReference struct {
	URL string `json:"url"` // Draft video URL
}

type requestPayload struct {
	Model                 string         `json:"model"`
	Content               []ContentItem  `json:"content"`
	CallbackURL           string         `json:"callback_url,omitempty"`
	ReturnLastFrame       *dto.BoolValue `json:"return_last_frame,omitempty"`
	ServiceTier           string         `json:"service_tier,omitempty"`
	ExecutionExpiresAfter dto.IntValue   `json:"execution_expires_after,omitempty"`
	GenerateAudio         *dto.BoolValue `json:"generate_audio,omitempty"`
	Draft                 *dto.BoolValue `json:"draft,omitempty"`
	Resolution            string         `json:"resolution,omitempty"`
	Ratio                 string         `json:"ratio,omitempty"`
	Duration              dto.IntValue   `json:"duration,omitempty"`
	Frames                dto.IntValue   `json:"frames,omitempty"`
	Seed                  dto.IntValue   `json:"seed,omitempty"`
	CameraFixed           *dto.BoolValue `json:"camera_fixed,omitempty"`
	Watermark             *dto.BoolValue `json:"watermark,omitempty"`
}

type responsePayload struct {
	ID string `json:"id"` // task_id
}

type responseTask struct {
	ID      string `json:"id"`
	Model   string `json:"model"`
	Status  string `json:"status"`
	Content struct {
		VideoURL string `json:"video_url"`
	} `json:"content"`
	Seed            int    `json:"seed"`
	Resolution      string `json:"resolution"`
	Duration        int    `json:"duration"`
	Ratio           string `json:"ratio"`
	FramesPerSecond int    `json:"framespersecond"`
	ServiceTier     string `json:"service_tier"`
	Usage           struct {
		CompletionTokens int `json:"completion_tokens"`
		TotalTokens      int `json:"total_tokens"`
	} `json:"usage"`
	CreatedAt int64 `json:"created_at"`
	UpdatedAt int64 `json:"updated_at"`
}

// ============================
// Adaptor implementation
// ============================

type TaskAdaptor struct {
	taskcommon.BaseBilling
	ChannelType int
	apiKey      string
	baseURL     string
}

func (a *TaskAdaptor) Init(info *relaycommon.RelayInfo) {
	a.ChannelType = info.ChannelType
	a.baseURL = info.ChannelBaseUrl
	a.apiKey = info.ApiKey
}

// ValidateRequestAndSetAction parses body, validates fields and sets default action.
func (a *TaskAdaptor) ValidateRequestAndSetAction(c *gin.Context, info *relaycommon.RelayInfo) (taskErr *dto.TaskError) {
	// Accept only POST /v1/video/generations as "generate" action.
	return relaycommon.ValidateBasicTaskRequest(c, info, constant.TaskActionGenerate)
}

// BuildRequestURL constructs the upstream URL.
func (a *TaskAdaptor) BuildRequestURL(info *relaycommon.RelayInfo) (string, error) {
	return fmt.Sprintf("%s/api/v3/contents/generations/tasks", a.baseURL), nil
}

// BuildRequestHeader sets required headers.
func (a *TaskAdaptor) BuildRequestHeader(c *gin.Context, req *http.Request, info *relaycommon.RelayInfo) error {
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Authorization", "Bearer "+a.apiKey)
	return nil
}

// BuildRequestBody converts request into Doubao specific format.
func (a *TaskAdaptor) BuildRequestBody(c *gin.Context, info *relaycommon.RelayInfo) (io.Reader, error) {
	req, err := relaycommon.GetTaskRequest(c)
	if err != nil {
		return nil, err
	}

	body, err := a.convertToRequestPayload(&req)
	if err != nil {
		return nil, errors.Wrap(err, "convert request payload failed")
	}
	if info.IsModelMapped {
		body.Model = info.UpstreamModelName
	} else {
		info.UpstreamModelName = body.Model
	}
	data, err := common.Marshal(body)
	if err != nil {
		return nil, err
	}
	return bytes.NewReader(data), nil
}

// DoRequest delegates to common helper.
func (a *TaskAdaptor) DoRequest(c *gin.Context, info *relaycommon.RelayInfo, requestBody io.Reader) (*http.Response, error) {
	return channel.DoTaskApiRequest(a, c, info, requestBody)
}

// DoResponse handles upstream response, returns taskID etc.
func (a *TaskAdaptor) DoResponse(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo) (taskID string, taskData []byte, taskErr *dto.TaskError) {
	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		taskErr = service.TaskErrorWrapper(err, "read_response_body_failed", http.StatusInternalServerError)
		return
	}
	_ = resp.Body.Close()

	// Parse Doubao response
	var dResp responsePayload
	if err := common.Unmarshal(responseBody, &dResp); err != nil {
		taskErr = service.TaskErrorWrapper(errors.Wrapf(err, "body: %s", responseBody), "unmarshal_response_body_failed", http.StatusInternalServerError)
		return
	}

	if dResp.ID == "" {
		taskErr = service.TaskErrorWrapper(fmt.Errorf("task_id is empty"), "invalid_response", http.StatusInternalServerError)
		return
	}

	ov := dto.NewOpenAIVideo()
	ov.ID = info.PublicTaskID
	ov.TaskID = info.PublicTaskID
	ov.CreatedAt = time.Now().Unix()
	ov.Model = info.OriginModelName

	c.JSON(http.StatusOK, ov)
	return dResp.ID, responseBody, nil
}

// FetchTask fetch task status
func (a *TaskAdaptor) FetchTask(baseUrl, key string, body map[string]any, proxy string) (*http.Response, error) {
	taskID, ok := body["task_id"].(string)
	if !ok {
		return nil, fmt.Errorf("invalid task_id")
	}

	uri := fmt.Sprintf("%s/api/v3/contents/generations/tasks/%s", baseUrl, taskID)

	req, err := http.NewRequest(http.MethodGet, uri, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+key)

	client, err := service.GetHttpClientWithProxy(proxy)
	if err != nil {
		return nil, fmt.Errorf("new proxy http client failed: %w", err)
	}
	return client.Do(req)
}

func (a *TaskAdaptor) GetModelList() []string {
	return ModelList
}

func (a *TaskAdaptor) GetChannelName() string {
	return ChannelName
}

// EstimateBilling 根据请求参数返回 Seedance SKU 倍率，用于预扣费。
func (a *TaskAdaptor) EstimateBilling(c *gin.Context, info *relaycommon.RelayInfo) map[string]float64 {
	req, err := relaycommon.GetTaskRequest(c)
	if err != nil {
		return nil
	}

	// 优先从顶层字段读取 resolution，fallback 到 metadata
	var resolution string
	if req.Resolution != "" {
		resolution = req.Resolution
	} else if req.Metadata != nil {
		if res, ok := req.Metadata["resolution"].(string); ok {
			resolution = res
		}
	}
	if resolution == "" {
		resolution = "720p"
	}

	hasVideoRef := req.HasVideo()

	sku := ResolveSeedanceSKU(resolution, hasVideoRef)

	return map[string]float64{SeedanceOtherRatioKey: sku}
}

// AdjustBillingOnComplete 任务完成时根据实际 token 数和 SKU 倍率计算最终费用。
// 返回正数触发差额结算，返回 0 保持预扣费不变。
func (a *TaskAdaptor) AdjustBillingOnComplete(task *model.Task, taskResult *relaycommon.TaskInfo) int {
	if taskResult.TotalTokens <= 0 {
		return 0
	}

	// 读取提交时存储的 SKU 倍率
	var skuMultiplier float64
	if bc := task.PrivateData.BillingContext; bc != nil {
		if sku, ok := bc.OtherRatios[SeedanceOtherRatioKey]; ok && sku > 0 {
			skuMultiplier = sku
		}
	}
	if skuMultiplier <= 0 {
		skuMultiplier = 1.0
	}

	// 获取基础模型倍率
	modelName := taskModelName(task)
	modelRatio, hasRatio, _ := ratio_setting.GetModelRatio(modelName)
	if !hasRatio || modelRatio <= 0 {
		modelRatio = seedanceBaseModelRatio
	}

	// 获取分组倍率
	group := task.Group
	if group == "" {
		user, err := model.GetUserById(task.UserId, false)
		if err == nil {
			group = user.Group
		}
	}
	if group == "" {
		return 0
	}
	groupRatio := ratio_setting.GetGroupRatio(group)
	userGroupRatio, hasUserGroupRatio := ratio_setting.GetGroupGroupRatio(group, group)
	if hasUserGroupRatio {
		groupRatio = userGroupRatio
	}

	// 最终费用 = totalTokens × modelRatio × skuMultiplier × groupRatio
	actualQuota := int(float64(taskResult.TotalTokens) * modelRatio * skuMultiplier * groupRatio)
	return actualQuota
}

// taskModelName 从 BillingContext 或 Properties 中获取模型名称。
func taskModelName(task *model.Task) string {
	if bc := task.PrivateData.BillingContext; bc != nil && bc.OriginModelName != "" {
		return bc.OriginModelName
	}
	return task.Properties.OriginModelName
}

func (a *TaskAdaptor) convertToRequestPayload(req *relaycommon.TaskSubmitReq) (*requestPayload, error) {
	r := requestPayload{
		Model:   req.Model,
		Content: []ContentItem{},
	}

	// Add text prompt
	if req.Prompt != "" {
		r.Content = append(r.Content, ContentItem{
			Type: "text",
			Text: req.Prompt,
		})
	}

	// Add images if present
	if req.HasImage() {
		for _, imgURL := range req.Images {
			r.Content = append(r.Content, ContentItem{
				Type: "image_url",
				ImageURL: &ImageURL{
					URL: imgURL,
				},
			})
		}
	}

	// Add videos if present (video references for seedance)
	if req.HasVideo() {
		for _, vidURL := range req.Videos {
			r.Content = append(r.Content, ContentItem{
				Type: "video",
				Video: &VideoReference{
					URL: vidURL,
				},
			})
		}
	}

	// 从顶层字段读取（对齐官方 API 格式）
	if req.Resolution != "" {
		r.Resolution = req.Resolution
	}
	if req.Ratio != "" {
		r.Ratio = req.Ratio
	}
	if req.Duration > 0 {
		r.Duration = dto.IntValue(req.Duration)
	}

	// metadata 作为 fallback / 覆盖（向后兼容）
	metadata := req.Metadata
	if err := taskcommon.UnmarshalMetadata(metadata, &r); err != nil {
		return nil, errors.Wrap(err, "unmarshal metadata failed")
	}

	return &r, nil
}

func (a *TaskAdaptor) ParseTaskResult(respBody []byte) (*relaycommon.TaskInfo, error) {
	resTask := responseTask{}
	if err := common.Unmarshal(respBody, &resTask); err != nil {
		return nil, errors.Wrap(err, "unmarshal task result failed")
	}

	taskResult := relaycommon.TaskInfo{
		Code: 0,
	}

	// Map Doubao status to internal status
	switch resTask.Status {
	case "pending", "queued":
		taskResult.Status = model.TaskStatusQueued
		taskResult.Progress = "10%"
	case "processing", "running":
		taskResult.Status = model.TaskStatusInProgress
		taskResult.Progress = "50%"
	case "succeeded":
		taskResult.Status = model.TaskStatusSuccess
		taskResult.Progress = "100%"
		taskResult.Url = resTask.Content.VideoURL
		// 解析 usage 信息用于按倍率计费
		taskResult.CompletionTokens = resTask.Usage.CompletionTokens
		taskResult.TotalTokens = resTask.Usage.TotalTokens
	case "failed":
		taskResult.Status = model.TaskStatusFailure
		taskResult.Progress = "100%"
		taskResult.Reason = "task failed"
	default:
		// Unknown status, treat as processing
		taskResult.Status = model.TaskStatusInProgress
		taskResult.Progress = "30%"
	}

	return &taskResult, nil
}

func (a *TaskAdaptor) ConvertToOpenAIVideo(originTask *model.Task) ([]byte, error) {
	var dResp responseTask
	if err := common.Unmarshal(originTask.Data, &dResp); err != nil {
		return nil, errors.Wrap(err, "unmarshal doubao task data failed")
	}

	openAIVideo := dto.NewOpenAIVideo()
	openAIVideo.ID = originTask.TaskID
	openAIVideo.TaskID = originTask.TaskID
	openAIVideo.Status = originTask.Status.ToVideoStatus()
	openAIVideo.SetProgressStr(originTask.Progress)
	openAIVideo.SetMetadata("url", dResp.Content.VideoURL)
	openAIVideo.CreatedAt = originTask.CreatedAt
	openAIVideo.CompletedAt = originTask.UpdatedAt
	openAIVideo.Model = originTask.Properties.OriginModelName

	if dResp.Status == "failed" {
		openAIVideo.Error = &dto.OpenAIVideoError{
			Message: "task failed",
			Code:    "failed",
		}
	}

	return common.Marshal(openAIVideo)
}
