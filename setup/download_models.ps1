<#
    ComfyUI modellarini yuklash (Qwen-Image-2.1) - ~11 GB.

    Har bir fayl hajmi tekshiriladi: to'g'ri bo'lsa o'tkaziladi,
    qisman yuklangan bo'lsa davom ettiriladi (curl -C -).

    .\download_models.ps1              faqat ComfyUI modellari
    .\download_models.ps1 -ComfyOnly   xuddi shu
    .\download_models.ps1 -TrellisOnly faqat TRELLIS.2 GGUF (Image-To-3D uchun)
#>
[CmdletBinding()]
param(
    [switch]$ComfyOnly,
    [switch]$TrellisOnly
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$Ws = Split-Path -Parent $Root

$Comfy = @(
    @{ Url = 'https://huggingface.co/Abiray/Qwen-Image-2.1-GGUF/resolve/main/qwen_image_2.1_Q4_K_M.gguf'
       Sub = 'ComfyUI\models\unet'
       Name = 'qwen_image_2.1_Q4_K_M.gguf'
       Size = 4189343904 }
    @{ Url = 'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_w4a8.safetensors'
       Sub = 'ComfyUI\models\text_encoders'
       Name = 'qwen3vl_8b_w4a8.safetensors'
       Size = 6312105364 }
    @{ Url = 'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors'
       Sub = 'ComfyUI\models\vae'
       Name = 'qwen_image_2.1_vae_bf16.safetensors'
       Size = 675509688 }
)

# TRELLIS.2 GGUF - Image-To-3D provision.ps1 ham xuddi shularni yuklaydi,
# shuning uchun bu ro'yxat faqat "faqat modellar" rejimi uchun.
$Trellis = @(
    @{ Repo = 'LocalAI-io/dinov3-vitl16-pretrain-lvd1689m-GGUF'; Name = 'dino_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS-image-large-GGUF';              Name = 'ss_dec_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'ss_flow_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'slat_flow_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'slat_flow_1024_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'shape_dec_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'shape_enc_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'tex_dec_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'tex_slat_flow_512_f16.gguf' }
    @{ Repo = 'LocalAI-io/TRELLIS.2-4B-GGUF';                    Name = 'tex_slat_flow_1024_f16.gguf' }
)

function Get-RemoteSize([string]$url) {
    try {
        $r = Invoke-WebRequest -Uri $url -Method Head -MaximumRedirection 5 -UseBasicParsing -TimeoutSec 30
        $len = $r.Headers['x-linked-size']
        if (-not $len) { $len = $r.Headers['Content-Length'] }
        return [int64]$len
    } catch { return 0 }
}

function Save-File([string]$url, [string]$dest, [int64]$expect) {
    $name = Split-Path $dest -Leaf
    if (Test-Path $dest) {
        $have = (Get-Item $dest).Length
        if ($have -ge $expect) {
            Write-Host "  [ok]   $name (allaqachon bor)" -ForegroundColor Green
            return $true
        }
        Write-Host "  [..]   $name davom ettirilmoqda ($have / $expect bayt)" -ForegroundColor Gray
    } else {
        Write-Host "  [..]   $name yuklanmoqda ($([math]::Round($expect/1GB,2)) GB)" -ForegroundColor Gray
    }

    $dir = Split-Path -Parent $dest
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    # curl barqarorroq (resume + retry) va Windows 10+ da mavjud
    & curl.exe -L -C - --retry 5 --retry-delay 5 --fail -o $dest $url
    if (-not (Test-Path $dest)) {
        Write-Host "  [FAIL] $name yuklanmadi" -ForegroundColor Red
        return $false
    }
    $have = (Get-Item $dest).Length
    if ($expect -gt 0 -and $have -lt $expect) {
        Write-Host "  [FAIL] $name hajmi to'g'ri kelmadi ($have / $expect)" -ForegroundColor Red
        return $false
    }
    Write-Host "  [ok]   $name" -ForegroundColor Green
    return $true
}

$failed = @()

if (-not $TrellisOnly) {
    Write-Host "`n=== ComfyUI modellari (Qwen-Image-2.1) - ~11 GB" -ForegroundColor Cyan
    foreach ($m in $Comfy) {
        $dest = Join-Path $Ws $m.Sub $m.Name
        if (-not (Save-File $m.Url $dest $m.Size)) { $failed += $m.Name }
    }
}

if (-not $ComfyOnly) {
    Write-Host "`n=== TRELLIS.2 modellari - ~15 GB" -ForegroundColor Cyan
    foreach ($m in $Trellis) {
        $url = "https://huggingface.co/$($m.Repo)/resolve/main/$($m.Name)"
        $dest = Join-Path $Ws "Image-To-3D\models" $m.Name
        $size = Get-RemoteSize $url
        if (-not (Save-File $url $dest $size)) { $failed += $m.Name }
    }
}

Write-Host ''
if ($failed.Count) {
    Write-Host "[FAIL] yuklanmagan: $($failed -join ', ')" -ForegroundColor Red
    Write-Host '       Internetni tekshirib, skriptni qayta ishga tushiring (yuklash davom etadi).'
    exit 1
}
Write-Host 'Barcha modellar tayyor.' -ForegroundColor Green
exit 0