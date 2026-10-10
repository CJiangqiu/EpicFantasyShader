"""用隐藏的 Windows 兼容模式上下文进行着色器编译与 GPU 验证。"""

import ctypes as c
import os
from ctypes import wintypes as w


class PixelFormat(c.Structure):
    _fields_ = [("size", w.WORD), ("version", w.WORD), ("flags", w.DWORD),
                ("pixel_type", c.c_ubyte), ("color_bits", c.c_ubyte),
                *[(name, c.c_ubyte) for name in (
                    "red_bits", "red_shift", "green_bits", "green_shift",
                    "blue_bits", "blue_shift", "alpha_bits", "alpha_shift",
                    "accum_bits", "accum_red", "accum_green", "accum_blue",
                    "accum_alpha", "depth_bits", "stencil_bits", "aux_buffers",
                    "layer_type", "reserved")],
                ("layer_mask", w.DWORD), ("visible_mask", w.DWORD),
                ("damage_mask", w.DWORD)]


class GLContext:
    def __init__(self, load_resources=True):
        if os.name != "nt":
            raise RuntimeError("GPU checks require Windows OpenGL.")
        self.user = c.WinDLL("user32", use_last_error=True)
        self.gdi = c.WinDLL("gdi32", use_last_error=True)
        self.opengl = c.WinDLL("opengl32", use_last_error=True)
        self.cache = {}
        self.load_resources = load_resources
        self.noise_texture = None
        self.window = self.dc = self.context = None
        self.user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                             c.c_int, c.c_int, c.c_int, c.c_int,
                                             w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p]
        self.user.CreateWindowExW.restype = w.HWND
        self.user.GetDC.argtypes = [w.HWND]
        self.user.GetDC.restype = w.HDC
        self.user.ReleaseDC.argtypes = [w.HWND, w.HDC]
        self.user.DestroyWindow.argtypes = [w.HWND]
        self.gdi.ChoosePixelFormat.argtypes = [w.HDC, c.POINTER(PixelFormat)]
        self.gdi.SetPixelFormat.argtypes = [w.HDC, c.c_int, c.POINTER(PixelFormat)]
        self.opengl.wglCreateContext.argtypes = [w.HDC]
        self.opengl.wglCreateContext.restype = c.c_void_p
        self.opengl.wglMakeCurrent.argtypes = [w.HDC, c.c_void_p]
        self.opengl.wglDeleteContext.argtypes = [c.c_void_p]
        self.opengl.wglGetProcAddress.argtypes = [c.c_char_p]
        self.opengl.wglGetProcAddress.restype = c.c_void_p
        try:
            self.window = self.user.CreateWindowExW(0, "STATIC", "Shader validation", 0,
                                                    0, 0, 16, 16, None, None, None, None)
            if not self.window:
                raise RuntimeError("Cannot create hidden OpenGL window.")
            self.dc = self.user.GetDC(self.window)
            fmt = PixelFormat()
            fmt.size, fmt.version = c.sizeof(fmt), 1
            fmt.flags, fmt.color_bits, fmt.depth_bits = 0x24, 32, 24
            pixel_format = self.gdi.ChoosePixelFormat(self.dc, c.byref(fmt))
            if not pixel_format or not self.gdi.SetPixelFormat(self.dc, pixel_format, c.byref(fmt)):
                raise RuntimeError("Cannot select OpenGL pixel format.")
            self.context = self.opengl.wglCreateContext(self.dc)
            if not self.context or not self.opengl.wglMakeCurrent(self.dc, self.context):
                raise RuntimeError("Cannot activate OpenGL context.")
        except Exception:
            self.close()
            raise

    def function(self, name, result, *arguments):
        if name not in self.cache:
            address = self.opengl.wglGetProcAddress(name.encode("ascii"))
            if address and address not in (1, 2, 3, c.c_void_p(-1).value):
                function = c.WINFUNCTYPE(result, *arguments)(address)
            else:
                function = getattr(self.opengl, name)
                function.restype, function.argtypes = result, arguments
            self.cache[name] = function
        return self.cache[name]

    def description(self):
        get = self.function("glGetString", c.c_char_p, c.c_uint)
        return " | ".join(get(token).decode() for token in (0x1F00, 0x1F01, 0x1F02))

    def program(self, vertex, fragment, feedback=()):
        shaders = []
        program = 0
        try:
            for kind, source in ((0x8B31, vertex), (0x8B30, fragment)):
                shader = self.function("glCreateShader", c.c_uint, c.c_uint)(kind)
                shaders.append(shader)
                encoded = c.c_char_p(source.encode("utf-8"))
                self.function("glShaderSource", None, c.c_uint, c.c_int,
                              c.POINTER(c.c_char_p), c.POINTER(c.c_int))(shader, 1, c.byref(encoded), None)
                self.function("glCompileShader", None, c.c_uint)(shader)
                status = c.c_int()
                self.function("glGetShaderiv", None, c.c_uint, c.c_uint,
                              c.POINTER(c.c_int))(shader, 0x8B81, c.byref(status))
                if not status.value:
                    log = c.create_string_buffer(32768)
                    self.function("glGetShaderInfoLog", None, c.c_uint, c.c_int,
                                  c.POINTER(c.c_int), c.c_void_p)(shader, len(log), None, log)
                    raise RuntimeError(log.value.decode(errors="replace"))
            program = self.function("glCreateProgram", c.c_uint)()
            for shader in shaders:
                self.function("glAttachShader", None, c.c_uint, c.c_uint)(program, shader)
            if feedback:
                names = (c.c_char_p * len(feedback))(*(name.encode() for name in feedback))
                self.function("glTransformFeedbackVaryings", None, c.c_uint, c.c_int,
                              c.POINTER(c.c_char_p), c.c_uint)(program, len(feedback), names, 0x8C8C)
            self.function("glLinkProgram", None, c.c_uint)(program)
            status = c.c_int()
            self.function("glGetProgramiv", None, c.c_uint, c.c_uint,
                          c.POINTER(c.c_int))(program, 0x8B82, c.byref(status))
            if not status.value:
                log = c.create_string_buffer(32768)
                self.function("glGetProgramInfoLog", None, c.c_uint, c.c_int,
                              c.POINTER(c.c_int), c.c_void_p)(program, len(log), None, log)
                raise RuntimeError(log.value.decode(errors="replace"))
            if self.load_resources:
                self.bind_noise_resource(program)
            return program
        except Exception:
            if program:
                self.delete_program(program)
            raise
        finally:
            for shader in shaders:
                self.function("glDeleteShader", None, c.c_uint)(shader)

    def delete_program(self, program):
        self.function("glDeleteProgram", None, c.c_uint)(program)

    def bind_noise_resource(self, program):
        """离线绘制使用发布包中的同一张噪声纹理，保留调用方绑定状态。"""
        location = self.function('glGetUniformLocation', c.c_int, c.c_uint, c.c_char_p)(program, b'noisetex')
        if location < 0:
            return
        from pathlib import Path
        from PIL import Image
        integer = self.function('glGetIntegerv', None, c.c_uint, c.POINTER(c.c_int))
        active, previous = c.c_int(), c.c_int()
        integer(0x84E0, c.byref(active))
        integer(0x8B8D, c.byref(previous))
        self.function('glActiveTexture', None, c.c_uint)(0x84C0 + 15)
        if self.noise_texture is None:
            texture = c.c_uint()
            self.function('glGenTextures', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(texture))
            self.noise_texture = texture
            self.function('glBindTexture', None, c.c_uint, c.c_uint)(0x0DE1, texture.value)
            with Image.open(Path(__file__).resolve().parents[1] / 'shaders/textures/cloud_noise.png') as image:
                pixels = image.convert('RGBA').tobytes()
                self.function('glTexImage2D', None, c.c_uint, c.c_int, c.c_int, c.c_int, c.c_int,
                              c.c_int, c.c_uint, c.c_uint, c.c_void_p)(
                    0x0DE1, 0, 0x8058, image.width, image.height, 0, 0x1908, 0x1401, pixels)
            parameter = self.function('glTexParameteri', None, c.c_uint, c.c_uint, c.c_int)
            for name, value in ((0x2801,0x2600),(0x2800,0x2600),(0x2802,0x812F),(0x2803,0x812F)):
                parameter(0x0DE1, name, value)
        else:
            self.function('glBindTexture', None, c.c_uint, c.c_uint)(0x0DE1, self.noise_texture.value)
        self.function('glUseProgram', None, c.c_uint)(program)
        self.function('glUniform1i', None, c.c_int, c.c_int)(location, 15)
        self.function('glUseProgram', None, c.c_uint)(previous.value)
        self.function('glActiveTexture', None, c.c_uint)(active.value)

    def close(self):
        if self.context:
            if self.noise_texture is not None:
                self.function('glDeleteTextures', None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(self.noise_texture))
                self.noise_texture = None
            self.opengl.wglMakeCurrent(None, None)
            self.opengl.wglDeleteContext(self.context)
            self.context = None
        if self.dc:
            self.user.ReleaseDC(self.window, self.dc)
            self.dc = None
        if self.window:
            self.user.DestroyWindow(self.window)
            self.window = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
