package service

import (
	"github.com/zhuimeng2026-hub/new-api/setting/operation_setting"
	"github.com/zhuimeng2026-hub/new-api/setting/system_setting"
)

func GetCallbackAddress() string {
	if operation_setting.CustomCallbackAddress == "" {
		return system_setting.ServerAddress
	}
	return operation_setting.CustomCallbackAddress
}
