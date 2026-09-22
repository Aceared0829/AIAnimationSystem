"""已知关键帧的离线姿态约束投影；原模型输出保留，不改变权重。"""
import numpy as np
from scipy.spatial.transform import Rotation


def constrain_poses(soft, reference, source_frames, anchors, radius=8, smoothness=12.0):
    """在局部变换上求平滑残差，关键帧为等式约束；只读取指定源姿态。

    范围外残差为零。旋转在SO(3)的主值旋转向量空间平滑，随后指数映射。
    这是已知动作的后处理实验，不保证任意旋转/接触的物理连续性。
    """
    soft=np.asarray(soft,dtype=np.float64)
    reference=np.asarray(reference,dtype=np.float64)
    frames=np.asarray(source_frames)
    if soft.ndim != 3 or soft.shape[-1] != 7 or reference.shape != soft.shape or not soft.shape[0] or not soft.shape[1]:
        raise ValueError('姿态必须为相同的非空 [帧, 骨骼, 7] 数组')
    if frames.shape != (len(soft),) or not np.issubdtype(frames.dtype,np.integer) or np.any(np.diff(frames)!=1):
        raise ValueError('源帧必须是连续递增整数，不能重复或跳帧')
    if type(radius) is not int or radius < 1 or not np.isfinite(smoothness) or smoothness < 0:
        raise ValueError('修正半径须为正整数，平滑权重须非负且有限')
    anchors=list(anchors)
    if any(isinstance(a,(bool,np.bool_)) or not isinstance(a,(int,np.integer)) for a in anchors):
        raise ValueError('参考帧必须是整数')
    if not np.isfinite(soft).all() or not np.allclose(np.linalg.norm(soft[...,3:],axis=-1),1,atol=1e-5):
        raise ValueError('软姿态必须有限且包含单位四元数')
    n,j=soft.shape[:2]
    ids={int(f):i for i,f in enumerate(frames)}
    active=sorted(ids[a] for a in set(anchors) if a in ids)
    if not active:return soft.copy()
    if not np.isfinite(reference[active]).all() or not np.allclose(np.linalg.norm(reference[active,:,3:],axis=-1),1,atol=1e-5):
        raise ValueError('参考姿态必须有限且包含单位四元数')
    rotations=Rotation.from_quat(soft[...,3:].reshape(-1,4))
    targets=np.zeros((n,j,6))
    for i in active:
        targets[i,:,:3]=reference[i,:,:3]-soft[i,:,:3]
        targets[i,:,3:]=(Rotation.from_quat(reference[i,:,3:])*Rotation.from_quat(soft[i,:,3:]).inv()).as_rotvec()
    # 防止修正向整段动作无界传播；关键帧之外不读取真实姿态。
    fixed=np.array([min(abs(i-a) for a in active)>=radius or i in active for i in range(n)])
    second=np.diff(np.eye(n),n=2,axis=0)
    hessian=np.eye(n)+smoothness*(second.T@second)
    values=targets.reshape(n,-1)
    free=~fixed
    correction=values.copy()
    if free.any():correction[free]=np.linalg.solve(hessian[np.ix_(free,free)],-hessian[np.ix_(free,fixed)]@values[fixed])
    correction=correction.reshape(n,j,6)
    out=soft.copy();out[:,:,:3]+=correction[:,:,:3]
    out[:,:,3:]=(Rotation.from_rotvec(correction[:,:,3:].reshape(-1,3))*rotations).as_quat().reshape(n,j,4)
    # 消除对数/指数映射的舍入误差，等式约束在最后一次融合之后执行。
    out[active]=reference[active]
    return out


def rotation_errors(a,b):
    dot=np.abs(np.sum(a[...,3:]*b[...,3:],axis=-1))
    return np.rad2deg(2*np.arccos(np.clip(dot,0,1)))
