{{/*
Expand the name of the chart.
*/}}
{{- define "vigilops.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "vigilops.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "vigilops.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "vigilops.labels" -}}
helm.sh/chart: {{ include "vigilops.chart" . }}
{{ include "vigilops.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "vigilops.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vigilops.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "vigilops.backend.labels" -}}
{{ include "vigilops.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "vigilops.backend.selectorLabels" -}}
{{ include "vigilops.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "vigilops.frontend.labels" -}}
{{ include "vigilops.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "vigilops.frontend.selectorLabels" -}}
{{ include "vigilops.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
MCP labels
*/}}
{{- define "vigilops.mcp.labels" -}}
{{ include "vigilops.labels" . }}
app.kubernetes.io/component: mcp
{{- end }}

{{/*
MCP selector labels
*/}}
{{- define "vigilops.mcp.selectorLabels" -}}
{{ include "vigilops.selectorLabels" . }}
app.kubernetes.io/component: mcp
{{- end }}

{{/*
PostgreSQL labels
*/}}
{{- define "vigilops.postgresql.labels" -}}
{{ include "vigilops.labels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "vigilops.postgresql.selectorLabels" -}}
{{ include "vigilops.selectorLabels" . }}
app.kubernetes.io/component: postgresql
{{- end }}

{{/*
Redis labels
*/}}
{{- define "vigilops.redis.labels" -}}
{{ include "vigilops.labels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "vigilops.redis.selectorLabels" -}}
{{ include "vigilops.selectorLabels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
PostgreSQL host - returns bundled service name or external host
*/}}
{{- define "vigilops.postgresql.host" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" (include "vigilops.fullname" .) }}
{{- else }}
{{- .Values.postgresql.external.host }}
{{- end }}
{{- end }}

{{/*
PostgreSQL port
*/}}
{{- define "vigilops.postgresql.port" -}}
{{- if .Values.postgresql.enabled }}
{{- .Values.postgresql.service.port | toString }}
{{- else }}
{{- .Values.postgresql.external.port | toString }}
{{- end }}
{{- end }}

{{/*
PostgreSQL database name
*/}}
{{- define "vigilops.postgresql.database" -}}
{{- if .Values.postgresql.enabled }}
{{- .Values.postgresql.auth.database }}
{{- else }}
{{- .Values.postgresql.external.database }}
{{- end }}
{{- end }}

{{/*
PostgreSQL username
*/}}
{{- define "vigilops.postgresql.username" -}}
{{- if .Values.postgresql.enabled }}
{{- .Values.postgresql.auth.username }}
{{- else }}
{{- .Values.postgresql.external.username }}
{{- end }}
{{- end }}

{{/*
Redis host - returns bundled service name or external host
*/}}
{{- define "vigilops.redis.host" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis" (include "vigilops.fullname" .) }}
{{- else }}
{{- .Values.redis.external.host }}
{{- end }}
{{- end }}

{{/*
Redis port
*/}}
{{- define "vigilops.redis.port" -}}
{{- if .Values.redis.enabled }}
{{- .Values.redis.service.port | toString }}
{{- else }}
{{- .Values.redis.external.port | toString }}
{{- end }}
{{- end }}

{{/*
Container image with global registry
*/}}
{{- define "vigilops.image" -}}
{{- $registry := .global.imageRegistry -}}
{{- $repository := .image.repository -}}
{{- $tag := .image.tag | default "latest" -}}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{/*
Secret name for the application
*/}}
{{- define "vigilops.secretName" -}}
{{- printf "%s-secret" (include "vigilops.fullname" .) }}
{{- end }}

{{/*
ConfigMap name for the application
*/}}
{{- define "vigilops.configmapName" -}}
{{- printf "%s-config" (include "vigilops.fullname" .) }}
{{- end }}
