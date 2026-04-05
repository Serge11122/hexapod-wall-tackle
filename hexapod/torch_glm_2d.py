import torch
import math
from glm import vec2
from dataclasses import dataclass

def torch_zero():
    return torch.zeros(size=())

class tvec2:
    def __init__(self, *args, requires_grad=False):
        # print(f'{args=}')
        if len(args) == 0:
            self.xy = torch.zeros(size=(2,), dtype=float, requires_grad=requires_grad)
        elif len(args) == 1 and isinstance(args[0], torch.Tensor):
            assert len(args[0]) == 2
            self.xy = args[0]
        elif isinstance(args[0], torch.Tensor):
            assert len(args) == 2
            # for arg in args:
            #     print(f'{arg=} {arg.size()=}')
            self.xy = torch.stack(args)
        else:
            assert len(args) == 2
            self.xy = torch.tensor(args, dtype=float, requires_grad=requires_grad)

        self.x = self.xy[0]
        self.y = self.xy[1]

    def dot(self, other):
        assert isinstance(other, tvec2)
        return self.x * other.x + self.y * other.y

    def length_squared(self):
        return self.dot(self)

    # def cross(self, other):
    #     assert isinstance(other, tvec3)
    #     return tvec3(
    #         self.y * other.z - self.z * other.y,
    #         self.z * other.x - self.x * other.z,
    #         self.x * other.y - self.y * other.x,
    #     )

    def __add__(self, other):
        assert isinstance(other, tvec2)
        return tvec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        assert isinstance(other, tvec2)
        return tvec2(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        assert isinstance(other, (float, torch.Tensor))
        return tvec2(other * self.x, other * self.y)

    def __repr__(self):
        xy = self.numpy()
        return f'tvec2({xy[0]}, {xy[1]})'

    def numpy(self):
        return self.xy.detach().numpy()

    def glm(self):
        return vec2(self.numpy())



class tquat2:
    def __init__(self, *args, requires_grad=False):
        # print(f'tquat2 {args=} {len(args)=}')
        if len(args) == 0:
            self.ab = torch.tensor((1, 0), dtype=float, requires_grad=requires_grad)
        elif len(args) == 1 and isinstance(args[0], torch.Tensor):
            assert len(args[0]) == 2
            self.ab = args[0]
        elif isinstance(args[0], torch.Tensor):
            assert len(args) == 2
            # for arg in args:
            #     print(f'{arg=} {arg.size()=}')
            self.ab = torch.stack(args)
            # print(f'this case {self.ab=}')
        else:
            assert len(args) == 2
            self.ab = torch.tensor(args, dtype=float, requires_grad=requires_grad)

        self.a = self.ab[0]
        self.b = self.ab[1]

    def __repr__(self):
        ab = self.numpy()
        return f'tquat2(a={ab[0]}, b={ab[1]})'

    def __mul__(self, other):
        a, b, c, d = self.a, self.b, other.a, other.b
        return tquat2(a * c - b * d, a * d + b * c)


    def numpy(self):
        return self.ab.detach().numpy()

    # def glm(self):
    #     return vec2(self.numpy())

    def rotate_vector(self, v: tvec2):
        # Complex multiplication, assuming ||self|| = 1
        return tvec2(self.a * v.x - self.b * v.y, self.a * v.y + self.b * v.x)

    @staticmethod
    def from_angle_no_grad(theta):
        # From e^i*theta = cos(theta) + i * sin(theta)
        q = tquat2()
        with torch.no_grad():
            q.ab[0] = math.cos(theta)
            q.ab[1] = math.sin(theta)
        return q

    @staticmethod
    def from_angle(theta):
        return tquat2(torch.cos(theta), torch.sin(theta))

    def length_squared(self):
        return torch.sum(self.ab ** 2)


@dataclass
class Pose2d:
    p: tvec2 = tvec2()
    q: tquat2 = tquat2()

    @staticmethod
    def from_angle_no_grad(x, y, theta):
        return Pose2d(p=tvec2(x, y), q=tquat2.from_angle_no_grad(theta))

    @staticmethod
    def from_angle(x, y, theta):
        return Pose2d(p=tvec2(x, y), q=tquat2.from_angle(theta))

    def __mul__(self, other):
        if isinstance(other, Pose2d):
            return Pose2d(p=self.q.rotate_vector(other.p) + self.p, q=self.q * other.q)
        elif isinstance(other, tvec2):
            return self.q.rotate_vector(other) + self.p
        else:
            raise

    def draw(self, ax, linespec):
        zero, x_axis, y_axis = self * tvec2(0, 0), self * tvec2(1, 0), self * tvec2(0, 1)
        zero, x_axis, y_axis = zero.glm(), x_axis.glm(), y_axis.glm()
        ax.plot([zero.x, x_axis.x], [zero.y, x_axis.y], 'r' + linespec)
        ax.plot([zero.x, y_axis.x], [zero.y, y_axis.y], 'g' + linespec)


# For reference, matrix implementation
# @dataclass
# class Pose2d:
#     m: mat3 = mat3()
#
#     @staticmethod
#     def from_angle_no_grad(x, y, theta):
#         m = mat3(mat4(quat(vec3(0, 0, theta))))
#         m[2, 0] = x
#         m[2, 1] = y
#         # print(f'{m=}')
#         # print(f'{m*vec3(0, 0, 1)=}')
#         return Pose2d(m)
#
#     def __mul__(self, other):
#         if isinstance(other, Pose2d):
#             return Pose2d(self.m * other.m)
#         elif isinstance(other, vec2):
#             return vec2(self.m * vec3(other.x, other.y, 1.0))
#         else:
#             raise
#
#     def draw(self, ax, linespec):
#         zero, x_axis, y_axis = self * vec2(0, 0), self * vec2(1, 0), self * vec2(0, 1)
#         ax.plot([zero.x, x_axis.x], [zero.y, x_axis.y], 'r' + linespec)
#         ax.plot([zero.x, y_axis.x], [zero.y, y_axis.y], 'g' + linespec)

def test():
    v0 = tvec2()
    print(f'{v0=}')
    print(f'{v0.x=}')

    v1 = tvec2(1, 0)
    print(f'{v1=}')

    v2 = tvec2(v0.x + v1.x, v0.y + v1.y)
    print(f'{v2=}')

    q0 = tquat2()
    print(f'{q0=}')
    v3 = q0.rotate_vector(v1)
    print(f'{v3=}')

    q1 = tquat2.from_angle_no_grad(3.14/2)
    v4 = q1.rotate_vector(v1)
    print(f'{v4=}')


if __name__ == "__main__":
    test()