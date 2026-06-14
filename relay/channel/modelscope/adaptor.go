package modelscope

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/zhuimeng2026-hub/new-api/common"
	"github.com/zhuimeng2026-hub/new-api/dto"
	"github.com/zhuimeng2026-hub/new-api/logger"
	"github.com/zhuimeng2026-hub/new-api/relay/channel"
	relaycommon "github.com/zhuimeng2026-hub/new-api/relay/common"
	relayconstant "github.com/zhuimeng2026-hub/new-api/relay/constant"
	"github.com/zhuimeng2026-hub/new-api/service"
	"github.com/zhuimeng2026-hub/new-api/types"

	"github.com/gin-gonic/gin"
)

type Adaptor struct{}

type ModelScopeImageResponse struct {
	TaskStatus  string   `json:"task_status"`
	TaskID      string   `json:"task_id"`
	RequestID   string   `json:"request_id,omitempty"`
	Message     string   `json:"message,omitempty"`
	OutputImages []string `json:"output_images,omitempty"`
}

func (a *Adaptor) Init(info *relaycommon.RelayInfo) {}

func (a *Adaptor) GetRequestURL(info *relaycommon.RelayInfo) (string, error) {
	switch info.RelayMode {
	case relayconstant.RelayModeImagesGenerations:
		return fmt.Sprintf("%s/v1/images/generations", info.ChannelBaseUrl), nil
	default:
		return fmt.Sprintf("%s/v1/chat/completions", info.ChannelBaseUrl), nil
	}
}

func (a *Adaptor) SetupRequestHeader(c *gin.Context, req *http.Header, info *relaycommon.RelayInfo) error {
	req.Set("Authorization", "Bearer "+info.ApiKey)
	if info.IsStream {
		req.Set("Accept", "text/event-stream")
	}
	if info.RelayMode == relayconstant.RelayModeImagesGenerations {
		req.Set("X-ModelScope-Async-Mode", "true")
	}
	return nil
}

func (a *Adaptor) ConvertOpenAIRequest(c *gin.Context, info *relaycommon.RelayInfo, request *dto.GeneralOpenAIRequest) (any, error) {
	if request == nil {
		return nil, errors.New("request is nil")
	}
	return request, nil
}

func (a *Adaptor) ConvertRerankRequest(c *gin.Context, relayMode int, request dto.RerankRequest) (any, error) {
	return nil, errors.New("not implemented")
}

func (a *Adaptor) ConvertEmbeddingRequest(c *gin.Context, info *relaycommon.RelayInfo, request dto.EmbeddingRequest) (any, error) {
	return request, nil
}

func (a *Adaptor) ConvertAudioRequest(c *gin.Context, info *relaycommon.RelayInfo, request dto.AudioRequest) (io.Reader, error) {
	return nil, errors.New("not implemented")
}

func (a *Adaptor) ConvertImageRequest(c *gin.Context, info *relaycommon.RelayInfo, request dto.ImageRequest) (any, error) {
	if info.RelayMode == relayconstant.RelayModeImagesGenerations {
		return struct {
			Model  string `json:"model"`
			Prompt string `json:"prompt"`
			Size   string `json:"size,omitempty"`
			N      int    `json:"n,omitempty"`
		}{
			Model:  info.UpstreamModelName,
			Prompt: request.Prompt,
			Size:   request.Size,
			N:      1,
		}, nil
	}
	return nil, errors.New("not implemented")
}

func (a *Adaptor) DoRequest(c *gin.Context, info *relaycommon.RelayInfo, requestBody io.Reader) (any, error) {
	return channel.DoApiRequest(a, c, info, requestBody)
}

func (a *Adaptor) DoResponse(c *gin.Context, resp *http.Response, info *relaycommon.RelayInfo) (usage any, err *types.NewAPIError) {
	if info.RelayMode != relayconstant.RelayModeImagesGenerations {
		return channel.DoApiRequest(a, c, info, nil)
	}

	responseBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeReadResponseBodyFailed, http.StatusInternalServerError)
	}
	service.CloseResponseBodyGracefully(resp)

	var msResponse ModelScopeImageResponse
	if err := common.Unmarshal(responseBody, &msResponse); err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
	}

	if msResponse.Message != "" {
		return nil, types.NewError(errors.New(msResponse.Message), types.ErrorCodeBadResponse)
	}

	// If task already succeeded with images in the initial response
	if msResponse.TaskStatus == "SUCCEED" && len(msResponse.OutputImages) > 0 {
		return a.buildImageResponse(c, info, msResponse.OutputImages, responseBody)
	}

	// If task failed immediately
	if msResponse.TaskStatus == "FAILED" || msResponse.TaskStatus == "CANCELED" {
		return nil, types.NewError(errors.New("task failed: "+msResponse.TaskStatus), types.ErrorCodeBadResponse)
	}

	// Async: poll for task completion
	if msResponse.TaskID == "" {
		return nil, types.NewError(errors.New("no task_id in response"), types.ErrorCodeBadResponse)
	}

	imageURLs, pollErr := a.pollTask(c, info, msResponse.TaskID)
	if pollErr != nil {
		return nil, types.NewError(pollErr, types.ErrorCodeBadResponse)
	}

	return a.buildImageResponse(c, info, imageURLs, responseBody)
}

func (a *Adaptor) pollTask(c *gin.Context, info *relaycommon.RelayInfo, taskID string) ([]string, error) {
	pollInterval := 3 * time.Second
	maxPolls := 60 // 3s * 60 = 180s max wait

	for i := 0; i < maxPolls; i++ {
		time.Sleep(pollInterval)

		url := fmt.Sprintf("%s/v1/tasks/%s", info.ChannelBaseUrl, taskID)
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			logger.LogWarn(c, fmt.Sprintf("modelscope poll build request error: %v", err))
			continue
		}
		req.Header.Set("Authorization", "Bearer "+info.ApiKey)
		req.Header.Set("X-ModelScope-Task-Type", "image_generation")

		client := &http.Client{Timeout: 15 * time.Second}
		resp, err := client.Do(req)
		if err != nil {
			logger.LogWarn(c, fmt.Sprintf("modelscope poll request error: %v", err))
			continue
		}

		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			continue
		}

		var pollResp ModelScopeImageResponse
		if err := common.Unmarshal(body, &pollResp); err != nil {
			continue
		}

		logger.LogDebug(c, fmt.Sprintf("modelscope poll %d/%d: status=%s", i+1, maxPolls, pollResp.TaskStatus))

		switch pollResp.TaskStatus {
		case "SUCCEED":
			if len(pollResp.OutputImages) == 0 {
				return nil, errors.New("task succeeded but no output_images")
			}
			return pollResp.OutputImages, nil
		case "FAILED":
			return nil, fmt.Errorf("task failed: %s", pollResp.Message)
		case "CANCELED":
			return nil, errors.New("task canceled")
		}
	}

	return nil, fmt.Errorf("task polling timeout after %ds", int(pollInterval.Seconds())*maxPolls)
}

func (a *Adaptor) buildImageResponse(c *gin.Context, info *relaycommon.RelayInfo, imageURLs []string, originBody []byte) (*dto.Usage, *types.NewAPIError) {
	data := make([]dto.ImageData, len(imageURLs))
	for i, url := range imageURLs {
		data[i] = dto.ImageData{
			URL:           url,
			RevisedPrompt: "",
		}
	}

	imageResponse := dto.ImageResponse{
		Created:  info.StartTime.Unix(),
		Data:     data,
		Metadata: originBody,
	}

	jsonResponse, err := common.Marshal(imageResponse)
	if err != nil {
		return nil, types.NewOpenAIError(err, types.ErrorCodeBadResponseBody, http.StatusInternalServerError)
	}

	c.Writer.Header().Set("Content-Type", "application/json")
	_, _ = c.Writer.Write(jsonResponse)

	return nil, nil
}

func (a *Adaptor) GetModelList() []string {
	return []string{
		"Tongyi-MAI/Z-Image-Turbo",
		"Qwen/Qwen-Image",
		"Qwen/Qwen-Image-Edit",
	}
}

func (a *Adaptor) GetChannelName() string {
	return "ModelScope"
}

func (a *Adaptor) ConvertClaudeRequest(c *gin.Context, info *relaycommon.RelayInfo, request *dto.ClaudeRequest) (any, error) {
	return nil, errors.New("not implemented")
}

func (a *Adaptor) ConvertGeminiRequest(c *gin.Context, info *relaycommon.RelayInfo, request *dto.GeminiChatRequest) (any, error) {
	return nil, errors.New("not implemented")
}
