import os
import glob
import subprocess
import time

# --- 配置区 ---
# 如果你需要使用网络代理来访问苹果服务器，请在这里填写你的代理地址。
# 如果不需要，请将其设置为 None。
PROXY_URL = "http://127.0.0.1:7890"
# --- 配置区结束 ---

def find_ipsw_file():
    """查找当前目录下的IPSW文件"""
    ipsw_files = glob.glob("*.ipsw")
    if not ipsw_files:
        raise FileNotFoundError("错误: 在当前目录下未找到 .ipsw 文件。")
    if len(ipsw_files) > 1:
        print(f"警告: 找到多个 .ipsw 文件，将使用第一个: {ipsw_files[0]}")
    return ipsw_files[0]

def run_command(command):
    """执行命令并实时打印输出"""
    print(f"执行命令: {command}")
    
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        encoding='utf-8'
    )

    # 实时打印标准输出
    for stdout_line in iter(process.stdout.readline, ""):
        print(stdout_line, end="")
    process.stdout.close()

    # 收集并打印错误输出
    # 注意: ipsw工具即使成功也可能将创建文件的日志打印到stderr，所以我们将其视为常规信息打印
    stderr_output = process.stderr.read()
    if stderr_output:
        print("\n--- 工具输出 (来自Stderr) ---\n" + stderr_output.strip() + "\n--- 工具输出结束 ---\n")
    
    process.wait()

    if process.returncode != 0:
        error_msg = f"命令执行失败，返回码: {process.returncode}"
        print(error_msg)
        if "unexpected EOF" in stderr_output or "timeout" in stderr_output:
            print("提示: 错误包含 'unexpected EOF' 或 'timeout'，这通常是网络问题。")
            print("请检查网络连接，或在脚本顶部设置 PROXY_URL 变量来使用代理。")
        raise subprocess.CalledProcessError(process.returncode, command, output=None, stderr=stderr_output)


def main():
    try:
        # 1. 找到IPSW文件
        ipsw_file = find_ipsw_file()
        print(f"找到IPSW文件: {ipsw_file}\n")

        base_cmd_prefix = "ipsw"
        if PROXY_URL:
            base_cmd_prefix += f" --proxy {PROXY_URL}"

        # 2. 提取FCS密钥
        fcs_cmd = f"{base_cmd_prefix} extract \"{ipsw_file}\" --fcs-key"
        run_command(fcs_cmd)
        print("FCS密钥提取完成\n")
        
        time.sleep(1)
        
        # 3. 提取DMG文件系统
        dmg_cmd = f"{base_cmd_prefix} extract \"{ipsw_file}\" --dmg fs"
        run_command(dmg_cmd)
        print("DMG文件系统提取完成\n")
        
        time.sleep(1)
        
        # 4. 查找并准备文件
        print("正在查找密钥和待解密文件...")

        all_pem_files = glob.glob("**/*.dmg.aea.pem", recursive=True)
        if not all_pem_files:
            raise FileNotFoundError("错误: 未找到任何 .pem 密钥文件。请检查 '--fcs-key' 提取步骤是否成功。")

        pem_to_use = all_pem_files[0]
        if len(all_pem_files) > 1:
            print(f"警告: 找到多个 .pem 文件，将统一使用第一个进行解密: {pem_to_use}\n")
        else:
            print(f"找到通用密钥文件: {pem_to_use}\n")

        all_aea_files = [f for f in glob.glob("**/*.dmg.aea", recursive=True) if not f.endswith('.pem')]
        if not all_aea_files:
            raise FileNotFoundError("错误: 未找到任何 .dmg.aea 文件。请检查 '--dmg fs' 提取步骤是否成功。")
        
        print(f"找到 {len(all_aea_files)} 个待解密的 .dmg.aea 文件。\n")

        output_dir = "decrypted_dmg"
        os.makedirs(output_dir, exist_ok=True)
        print(f"解密后的文件将保存在 '{output_dir}' 目录中。\n")

        # 5. 循环解密所有AEA文件
        success_count = 0
        fail_count = 0
        for aea_file in all_aea_files:
            print(f"--- 正在处理 ---\nAEA: {aea_file}\n使用密钥: {pem_to_use}")
            
            # --- 关键修改在这里 ---
            # 之前: 我们构造了一个完整的文件路径作为输出
            # 现在: 我们只使用目录路径作为输出
            decrypt_cmd = f'ipsw fw aea --pem "{pem_to_use}" "{aea_file}" --output "{output_dir}"'
            
            # 为了打印正确的成功信息，我们预先计算出期望的输出文件路径
            decrypted_filename = os.path.basename(aea_file).replace(".aea", "")
            expected_output_path = os.path.join(output_dir, decrypted_filename)

            try:
                run_command(decrypt_cmd)
                # 检查文件是否真的被创建了
                if os.path.exists(expected_output_path):
                    print(f"成功解密 -> {expected_output_path}\n")
                    success_count += 1
                else:
                    # 有时候ipsw不报错但也没创建文件
                    print(f"警告: 命令执行完毕，但未在预期位置找到输出文件: {expected_output_path}\n")
                    fail_count += 1
            except subprocess.CalledProcessError:
                print(f"解密失败: {aea_file}\n")
                fail_count += 1
        
        print("------ 操作完成 ------")
        print(f"成功: {success_count} 个, 失败/跳过: {fail_count} 个")

    except FileNotFoundError as e:
        print(f"\n错误: {str(e)}")
        return 1
    except subprocess.CalledProcessError:
        print("\n错误: 由于上一步命令执行失败，脚本已终止。")
        return 1
    except Exception as e:
        print(f"\n发生未知错误: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)