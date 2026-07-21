#!/usr/bin/env python3
"""
Test Suite for Video Variations System
Verifica se o sistema está instalado e funcionando corretamente
"""

import subprocess
import sys
import os
import tempfile
import json
from pathlib import Path


class SystemTester:
    """Testa cada componente do sistema"""

    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.warnings = []

    def print_header(self, text):
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}")

    def print_test(self, name, passed, message=""):
        status = "✓ PASS" if passed else "✗ FAIL"
        self.tests_passed += passed
        self.tests_failed += not passed
        print(f"[{status}] {name}")
        if message:
            print(f"      └─ {message}")

    def test_python_version(self):
        """Testa se Python 3.8+ está instalado"""
        try:
            version = sys.version_info
            passed = version.major == 3 and version.minor >= 8
            self.print_test(
                "Python Version",
                passed,
                f"Python {version.major}.{version.minor}.{version.micro}"
            )
            return passed
        except Exception as e:
            self.print_test("Python Version", False, str(e))
            return False

    def test_ffmpeg_installed(self):
        """Testa se FFmpeg está instalado"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version_line = result.stdout.split("\n")[0]
                self.print_test("FFmpeg Installed", True, version_line)
                return True
            else:
                self.print_test("FFmpeg Installed", False, "FFmpeg não respondeu")
                return False
        except FileNotFoundError:
            self.print_test(
                "FFmpeg Installed",
                False,
                "FFmpeg não encontrado no PATH. Instale com: brew install ffmpeg"
            )
            return False
        except Exception as e:
            self.print_test("FFmpeg Installed", False, str(e))
            return False

    def test_ffprobe_installed(self):
        """Testa se FFprobe está instalado"""
        try:
            result = subprocess.run(
                ["ffprobe", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            passed = result.returncode == 0
            self.print_test("FFprobe Installed", passed)
            return passed
        except FileNotFoundError:
            self.warnings.append("FFprobe não encontrado (opcional, vem com FFmpeg)")
            self.print_test("FFprobe Installed", False, "Não encontrado (opcional)")
            return False

    def test_python_modules(self):
        """Testa se módulos Python necessários estão disponíveis"""
        required = ["json", "subprocess", "concurrent.futures", "pathlib"]
        all_passed = True

        for module in required:
            try:
                __import__(module)
                self.print_test(f"Module: {module}", True)
            except ImportError:
                self.print_test(f"Module: {module}", False, "Módulo não encontrado")
                all_passed = False

        return all_passed

    def test_file_permissions(self):
        """Testa se pode criar arquivos temporários"""
        try:
            with tempfile.NamedTemporaryFile(delete=True) as f:
                f.write(b"test")
                f.flush()
            self.print_test("File Permissions", True, "Pode criar arquivos temporários")
            return True
        except Exception as e:
            self.print_test("File Permissions", False, str(e))
            return False

    def test_disk_space(self):
        """Testa espaço em disco disponível"""
        try:
            import shutil
            stat = shutil.disk_usage("/tmp" if os.name != "nt" else "C:\\")
            free_gb = stat.free / (1024**3)
            passed = free_gb > 5  # Pelo menos 5GB

            message = f"{free_gb:.1f}GB disponível"
            if not passed:
                message += " (recomendado: ≥ 10GB)"

            self.print_test("Disk Space", passed, message)
            return passed
        except Exception as e:
            self.print_test("Disk Space", False, str(e))
            return False

    def test_video_creation(self):
        """Testa se pode criar um vídeo de teste com FFmpeg"""
        try:
            # Criar vídeo de teste (1 segundo)
            with tempfile.TemporaryDirectory() as tmpdir:
                test_video = os.path.join(tmpdir, "test.mp4")

                cmd = [
                    "ffmpeg",
                    "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
                    "-f", "lavfi", "-i", "sine=f=1000:d=1",
                    "-c:v", "libx264",
                    "-c:a", "aac",
                    "-y",
                    test_video
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0 and os.path.exists(test_video):
                    size_mb = os.path.getsize(test_video) / (1024**2)
                    self.print_test(
                        "Video Creation",
                        True,
                        f"Criou vídeo de teste ({size_mb:.1f}MB)"
                    )
                    return True
                else:
                    error = result.stderr[-200:] if result.stderr else "Desconhecido"
                    self.print_test("Video Creation", False, error)
                    return False

        except subprocess.TimeoutExpired:
            self.print_test("Video Creation", False, "Timeout")
            return False
        except Exception as e:
            self.print_test("Video Creation", False, str(e))
            return False

    def test_system_scripts(self):
        """Testa se scripts Python principais existem e são válidos"""
        scripts = [
            "video_variations_system.py",
            "video_variations_from_config.py"
        ]

        all_passed = True
        for script in scripts:
            if os.path.exists(script):
                try:
                    with open(script, 'r') as f:
                        content = f.read()
                    # Verificar sintaxe básica
                    compile(content, script, 'exec')
                    self.print_test(f"Script: {script}", True, "Sintaxe válida")
                except SyntaxError as e:
                    self.print_test(f"Script: {script}", False, f"Erro de sintaxe: {e}")
                    all_passed = False
            else:
                self.print_test(
                    f"Script: {script}",
                    False,
                    "Arquivo não encontrado"
                )
                all_passed = False

        return all_passed

    def test_output_directory(self):
        """Testa se pode criar diretório de saída"""
        try:
            os.makedirs("output", exist_ok=True)
            # Testar escrita
            test_file = os.path.join("output", ".test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)

            self.print_test("Output Directory", True, "output/ criado e acessível")
            return True
        except Exception as e:
            self.print_test("Output Directory", False, str(e))
            return False

    def run_all_tests(self):
        """Executa todos os testes"""
        self.print_header("🔧 Video Variations System — Test Suite")

        print("\n📋 Testando Dependências do Sistema...")
        self.test_python_version()
        self.test_ffmpeg_installed()
        self.test_ffprobe_installed()
        self.test_disk_space()

        print("\n📦 Testando Módulos Python...")
        self.test_python_modules()

        print("\n🔍 Testando Funcionalidades...")
        self.test_file_permissions()
        self.test_video_creation()
        self.test_system_scripts()
        self.test_output_directory()

        # Resumo
        self.print_header("📊 Resumo dos Testes")
        total = self.tests_passed + self.tests_failed
        print(f"\n✓ Passou: {self.tests_passed}/{total}")
        print(f"✗ Falhou: {self.tests_failed}/{total}")

        if self.warnings:
            print(f"\n⚠️  Avisos:")
            for warning in self.warnings:
                print(f"   • {warning}")

        print()

        if self.tests_failed == 0:
            print("✅ TODOS OS TESTES PASSARAM!")
            print("\n🚀 Sistema pronto para usar:")
            print("   python3 video_variations_system.py seu_video.mp4 -n 5")
            return True
        else:
            print("❌ ALGUNS TESTES FALHARAM")
            print("\n🔧 Corrija os problemas acima e tente novamente.")
            return False


def main():
    tester = SystemTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
