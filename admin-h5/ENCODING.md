# admin-h5 中文与编码规范

## 必须遵守

- 所有源码文件统一使用 UTF-8。
- 编辑器打开项目后，确认右下角编码为 `UTF-8`。
- 不要把 PowerShell `Get-Content` 的中文显示结果当作源码是否乱码的唯一判断依据；Windows PowerShell 5.x 默认编码页可能会把 UTF-8 中文显示成乱码。
- 页面中文是否正常，以浏览器渲染、`npm run check:text`、`npm run build` 为准。

## 每次开发后执行

```bash
npm run check
```

这个命令会先执行：

```bash
npm run check:text
```

用于扫描 `src` 下的 `.vue`、`.js`、`.ts`、`.css`、`.json` 文件，发现常见中文乱码、替换字符后会直接失败。

然后执行：

```bash
npm run build
```

用于检查 Vue 页面语法是否可以正常构建。

## Windows PowerShell 显示中文

如果只是 PowerShell 输出中文乱码，可以先执行：

```powershell
chcp 65001
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

更推荐使用 PowerShell 7 或 VS Code 终端，并保持终端编码为 UTF-8。
