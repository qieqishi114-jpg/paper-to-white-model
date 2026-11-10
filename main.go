package main

import (
	"bytes"
	"context"
	"embed"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

//go:embed index.html
var assets embed.FS

func main() {
	python := flag.String("python", "python", "Python executable")
	flag.Parse()
	slots := make(chan struct{}, 2)
	http.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFileFS(w, r, assets, "index.html")
	})
	http.HandleFunc("POST /build", func(w http.ResponseWriter, r *http.Request) {
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
		default:
			http.Error(w, "任务已满，请稍后重试", 429)
			return
		}
		r.Body = http.MaxBytesReader(w, r.Body, 24<<20)
		if err := r.ParseMultipartForm(24 << 20); err != nil {
			http.Error(w, "无法读取请求或文件过大", 400)
			return
		}
		defer r.MultipartForm.RemoveAll()
		work, err := os.MkdirTemp(".", "white-model-")
		if err != nil {
			http.Error(w, "无法建立任务目录", 500)
			return
		}
		defer os.RemoveAll(work)
		write := func(path string, data []byte) bool { return os.WriteFile(path, data, 0600) == nil }
		if !write(filepath.Join(work, "request.txt"), []byte(r.FormValue("request"))) ||
			!write(filepath.Join(work, "parameters.json"), []byte(r.FormValue("parameters"))) {
			http.Error(w, "无法保存请求", 500)
			return
		}
		source := ""
		if file, header, e := r.FormFile("source"); e == nil {
			defer file.Close()
			ext := strings.ToLower(filepath.Ext(header.Filename))
			switch ext {
			case ".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt":
			default:
				http.Error(w, "文件类型不支持", 400)
				return
			}
			source = filepath.Join(work, "source"+ext)
			out, e := os.OpenFile(source, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
			if e != nil {
				http.Error(w, "无法保存附件", 500)
				return
			}
			_, e = io.Copy(out, file)
			out.Close()
			if e != nil {
				http.Error(w, "无法保存附件", 500)
				return
			}
		} else if e != http.ErrMissingFile {
			http.Error(w, "附件读取失败", 400)
			return
		}
		mode := r.FormValue("mode")
		if mode != "preview" && mode != "export" {
			http.Error(w, "未知操作", 400)
			return
		}
		ctx, cancel := context.WithTimeout(r.Context(), 90*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, *python, "pipeline.py", work, source, mode)
		var stderr bytes.Buffer
		cmd.Stderr = &stderr
		result, e := cmd.Output()
		if ctx.Err() != nil {
			http.Error(w, "处理超时", 504)
			return
		}
		if e != nil {
			log.Print(stderr.String())
			http.Error(w, "处理失败，请查看终端日志", 500)
			return
		}
		var payload struct{ Error string }
		if json.Unmarshal(result, &payload) != nil {
			http.Error(w, "返回格式错误", 500)
			return
		}
		if payload.Error != "" {
			http.Error(w, payload.Error, 400)
			return
		}
		if mode == "export" {
			w.Header().Set("Content-Disposition", "attachment; filename=white-model.zip")
			http.ServeFile(w, r, filepath.Join(work, "white-model.zip"))
			return
		}
		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		w.Write(result)
	})
	server := &http.Server{Addr: "127.0.0.1:8787", ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 35 * time.Second, WriteTimeout: 110 * time.Second}
	fmt.Println("http://127.0.0.1:8787")
	log.Fatal(server.ListenAndServe())
}
