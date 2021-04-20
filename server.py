#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
from random import randint
from io import BytesIO
from shutil import copyfileobj
import threading
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from urllib.request import quote, unquote
from time import time
from hashlib import md5
from signal import signal, SIGPIPE, SIG_DFL, SIGCHLD, SIG_IGN
from PIL import Image
import base14, sys, os, img_diff, form_fsm

host = ('0.0.0.0', 80)
byte_succ = "succ".encode()
byte_erro = "erro".encode()
byte_null = "null".encode()

base14.init_dll('./build/libbase14.so')

def get_uuid():
	return base14.get_base14(md5(str(time()).encode()).digest())[:2]

class Resquest(BaseHTTPRequestHandler):
	def send_200(self, data, content_type):
		self.send_response(200)
		self.send_header('Content-type', content_type)
		self.end_headers()
		self.wfile.write(data)

	def do_pick(self, user_uuid: str, send_name_only: bool):
		if len(user_uuid) == 2:		#base14检测
			user_path = user_dir + user_uuid +'/'
			#print("User dir:", user_path)
			if os.path.exists(user_path):
				voted_imgs_list = os.listdir(user_path)
				all_imgs_list = [name[:-5] for name in os.listdir(image_dir)]
				all_imgs_len = len(all_imgs_list)
				if len(voted_imgs_list) < all_imgs_len:
					pick_img_name = all_imgs_list[randint(0, all_imgs_len-1)]
					while pick_img_name in voted_imgs_list:
						pick_img_name = all_imgs_list[randint(0, all_imgs_len-1)]
					if send_name_only: self.send_200(quote(pick_img_name).encode(), "text/plain")
					else:
						img_path = image_dir + pick_img_name + ".webp"
						try:
							with open(img_path, "rb") as f:
								self.send_200(f.read(), "image/webp")
						except: self.send_200(byte_erro, "text/plain")
				else: self.send_200(byte_null, "text/plain")
			else: self.send_200(byte_erro, "text/plain")
		else: self.send_200(byte_erro, "text/plain")

	def do_GET(self):
		get_path = self.path[1:]
		get_path_len = len(get_path)
		#print("get_path_len:", get_path_len)
		if get_path_len == 17 and get_path[:6] == "signup":	# 注册
			try:
				if abs(int(time()) - (int(get_path[7:]) ^ pwd)) <= 10:		#验证通过
					new_uuid = get_uuid()
					os.makedirs(user_dir + new_uuid)
					self.send_200(new_uuid.encode("utf-8"), "application/octet-stream")
				else: self.send_200(byte_null, "text/plain")
			except: self.send_200(byte_erro, "text/plain")
		elif get_path_len == 0 or (get_path_len == 10 and get_path == "index.html"):
			with open("./index.html", "rb") as f:
				self.send_200(f.read(), "text/html")
		elif get_path_len == 25 and get_path[:6] == "pickdl":
			self.do_pick(unquote(get_path[7:]), False)
		elif get_path_len == 23 and get_path[:4] == "pick":
			self.do_pick(unquote(get_path[5:]), True)
		elif get_path_len >= 72:		# 投票
			if get_path_len > 4 and get_path[:4] == "vote":
				try:
					cli_req = get_path[5:]
					cli_uuid = unquote(cli_req[5:23])
					if len(cli_uuid) == 2:			#base14检测
						cli_img = unquote(cli_req[28:73])
						if len(cli_img) == 5:		#base14检测
							cli_cls = cli_req[80:]
							print("uuid:", cli_uuid, "img:", cli_img, "class:", cli_cls)
							cli_dir = user_dir + cli_uuid + '/'
							#os.makedirs(cli_dir, exist_ok=True)
							with open(cli_dir + cli_img, "w") as f: f.write(cli_cls)
							self.send_200(byte_succ, "text/plain")
						else: self.send_200(byte_erro, "text/plain")
					else: self.send_200(byte_erro, "text/plain")
				except: self.send_200(byte_erro, "text/plain")
		elif get_path_len == 45:
			target_img_name = unquote(get_path)
			if len(target_img_name) == 5:		#base14检测
				img_path = image_dir + target_img_name + ".webp"
				#print("Get img:", img_path)
				if os.path.exists(img_path):
					try:
						with open(img_path, "rb") as f:
							self.send_200(f.read(), "image/webp")
					except: self.send_200(byte_erro, "text/plain")
				else: self.send_200(byte_null, "text/plain")
			else: self.send_200(byte_erro, "text/plain")
		else: self.send_200(byte_null, "text/plain")
	
	def do_POST(self):
		path_len = len(self.path)
		if path_len == 31 and self.path[:13] == "/upload?uuid=":			#上传图片
			cli_uuid = unquote(self.path[13:])
			if len(cli_uuid) == 2:
				if os.path.exists(user_dir + cli_uuid):
					self.save_img(self.rfile.read(int(self.headers.get('content-length'))))
				else: self.send_200(byte_null, "text/plain")
			else: self.send_200(byte_erro, "text/plain")
		elif path_len == 31 and self.path[:13] == "/upform?uuid=":		#表单上传图片
			cli_uuid = unquote(self.path[13:])
			if len(cli_uuid) == 2:
				if os.path.exists(user_dir + cli_uuid):
					size = int(self.headers.get('content-length'))
					skip = 0
					if size > 1024:
						state = 0
						while skip < 1024:
							skip += 1
							state = form_fsm.scan(state, self.rfile.read(1)[0])
							if state == 11:
								skip += 3
								self.rfile.read(3)
								self.do_form_post(size, skip)
								break
				else: self.send_200(byte_null, "text/plain")
			else: self.send_200(byte_erro, "text/plain")
		else: self.send_200(byte_null, "text/plain")

	def do_form_post(self, size: int, skip: int):
		skip += 9
		file_type = self.rfile.read(9).decode()
		print("post form type:", file_type)
		if file_type == "image/web" or file_type == "image/png" or file_type == "image/jpe":
			if file_type == "image/png":
				skip += 4
				self.rfile.read(4)
			else:
				skip += 5
				self.rfile.read(5)
			datas = self.rfile.read(size - skip - 46)		#掐头去尾
			self.save_img(datas)
		else: self.send_200(byte_erro, "text/plain")
	
	def save_img(self, datas: bytes):
		is_converted = False
		with Image.open(BytesIO(datas)) as img2save:
			if img2save.format != "WEBP":		#转换webp
				converted = BytesIO()
				img2save.save(converted, "WEBP")
				converted.seek(0)
				is_converted = True
		fname = img_diff.get_dhash_b14_io(converted) if is_converted else img_diff.get_dhash_b14(datas) 
		no_similar = True
		all_imgs_list = os.listdir(image_dir)
		this_hash = img_diff.decode_dhash(fname)
		hash_len = len(this_hash)
		for img_name in all_imgs_list:
			if img_diff.hamm_img(this_hash, img_diff.decode_dhash(img_name), hash_len) <= 12:
				no_similar = False
				break
		if no_similar:
			print("Recv file:", fname)
			fn = os.path.join(image_dir, fname + ".webp")	#生成文件存储路径
			if not os.path.exists(fn):
				if is_converted: converted.seek(0)
				with open(fn, 'wb') as f: copyfileobj(converted, f) if is_converted else f.write(datas)
				if is_converted: converted.close()
				self.send_200(byte_succ, "text/plain")
			else: self.send_200(byte_erro, "text/plain")
		else:  self.send_200(byte_null, "text/plain")

# Launch 100 listener threads.
class Thread(threading.Thread):
	def __init__(self, i: int):
		threading.Thread.__init__(self)
		self.i = i
		signal(SIGPIPE, SIG_DFL)		# 忽略管道错误
		self.daemon = True
		self.start()
	def run(self):
		self.httpd = HTTPServer(host, Resquest, False)
		# Prevent the HTTP server from re-binding every handler.
		# https://stackoverflow.com/questions/46210672/
		self.httpd.socket = sock
		self.httpd.server_bind = self.server_close = lambda self: None
		self.httpd.serve_forever()

if __name__ == '__main__':
	if len(sys.argv) == 4 or len(sys.argv) == 5:
		user_dir = sys.argv[1]
		image_dir = sys.argv[2]
		with open(sys.argv[3], "rb") as f:
			pwd = int.from_bytes(f.read()[2:], byteorder="big")		#两个汉字，四个字节
		if len(sys.argv) == 5: server_uid = int(sys.argv[4])
		if user_dir[-1] != '/': user_dir += '/'
		if os.path.exists(image_dir):
			if image_dir[-1] != '/': image_dir += '/'
			print("Starting ICQS at: %s:%s" % host, "storage dir:", user_dir, "image dir:", image_dir)
			# Create ONE socket.
			sock = socket(AF_INET, SOCK_STREAM)
			sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
			sock.bind(host)
			sock.listen(5)
			if len(sys.argv) == 5: os.setuid(server_uid)		#监听后降权
			if os.fork() == 0:		#创建daemon
				os.setsid()
				#创建孙子进程，而后子进程退出
				if os.fork() > 0:
   		 			sys.exit(0)
				#重定向标准输入流、标准输出流、标准错误
				sys.stdout.flush()
				sys.stderr.flush()
				si = open("/dev/null", 'r')
				so = open("/dev/null", 'a+')
				se = open("/dev/null", 'a+')
				os.dup2(si.fileno(), sys.stdin.fileno())
				os.dup2(so.fileno(), sys.stdout.fileno())
				os.dup2(se.fileno(), sys.stderr.fileno())
				signal(SIGCHLD, SIG_IGN)
				pid = os.fork()
				while pid:			#监控服务是否退出
					os.wait()
					print("Subprocess exited, restarting...")
					pid = os.fork()
				if pid < 0:
					print("Fork error!")
				else:
					[Thread(i) for i in range(100)]
					#主进程也开启一个服务
					signal(SIGPIPE, SIG_DFL)		# 忽略管道错误
					httpd = HTTPServer(host, Resquest, False)
					httpd.socket = sock
					httpd.server_bind = lambda self: None
					httpd.serve_forever()
		else: print("Error: image dir", image_dir, "is not exist.")
	else: print("Usage:", sys.argv[0], "<user_dir> <image_dir> <pwd_path> (server_uid)")