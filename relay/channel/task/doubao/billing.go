package doubao

// Seedance 2.0 SKU 倍率（基于 kapon 上游 doubao 国内版定价）
//
// ModelRatio 基础值 = 3.29（对应 720p 无视频参考 ¥46/M tokens）
// SKU 倍率用于区分不同分辨率和视频参考的定价差异
//
// 计费公式：
//
//	预扣费 = modelRatio(3.29) × QuotaPerUnit × groupRatio × seedance_sku
//	结算费 = totalTokens × modelRatio(3.29) × seedance_sku × groupRatio
//
// kapon 官方定价（doubao 国内版）：
//
//	720p 无视频参考: ¥46/M  → sku=1.0
//	1080p 无视频参考: ¥51/M  → sku=1.109
//	720p 有视频参考: ¥92/M  → sku=2.0
//	1080p 有视频参考: ¥102/M → sku=2.217

const (
	// seedanceBaseModelRatio 是 720p 无视频参考场景的基础倍率
	// 对应 kapon ¥46/M tokens: 46 / 7.3 / 2 * 1000 ≈ 3.29
	seedanceBaseModelRatio = 3.29

	// SKU 倍率：以 720p 无视频参考为基准
	seedanceSKU720pNoVideo  = 1.0         // ¥46/M
	seedanceSKU1080pNoVideo = 51.0 / 46.0 // ≈ 1.109
	seedanceSKU720pVideo    = 92.0 / 46.0 // = 2.0
	seedanceSKU1080pVideo   = 102.0 / 46.0 // ≈ 2.217
)

// SeedanceOtherRatioKey 是存储在 OtherRatios 中的 SKU 倍率 key
const SeedanceOtherRatioKey = "seedance_sku"

// ResolveSeedanceSKU 根据分辨率和是否有视频参考返回 SKU 倍率
func ResolveSeedanceSKU(resolution string, hasVideoRef bool) float64 {
	is1080p := resolution == "1080p"

	switch {
	case is1080p && hasVideoRef:
		return seedanceSKU1080pVideo
	case is1080p:
		return seedanceSKU1080pNoVideo
	case hasVideoRef:
		return seedanceSKU720pVideo
	default:
		return seedanceSKU720pNoVideo
	}
}
