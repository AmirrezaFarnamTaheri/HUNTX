{{- define "huntx-fleet.name" -}}{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}{{- end -}}
{{- define "huntx-fleet.fullname" -}}{{- printf "%s-%s" .Release.Name (include "huntx-fleet.name" .) | trunc 63 | trimSuffix "-" -}}{{- end -}}
