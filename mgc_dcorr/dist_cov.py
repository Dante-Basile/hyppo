from numba import njit, prange
import numpy as np
from numpy import linalg as LA

@njit(parallel=True)
def mean_numba_axis0(A):
    res = []
    for i in prange(A.shape[0]):
        res.append(A[:, i].mean())
    return np.array(res)

@njit(parallel=True)
def mean_numba_axis1(A):
    res = []
    for i in prange(A.shape[0]):
        res.append(A[i, :].mean())
    return np.array(res)

@njit(parallel=True)
def mean_numba_axis0_3d(A):
    N = A.shape[0]
    res = np.zeros((N, N))
    for i in prange(N):
        res[i] = mean_numba_axis1(A[:, i, :])
    return res

@njit(parallel=True)
def mean_numba_axis1_3d(A):
    N = A.shape[0]
    res = np.zeros((N, N))
    for i in prange(N):
        res[i] = mean_numba_axis1(A[i, :, :])
    return res

@njit(parallel=True)
def mean_numba_m_3d(A):
    N = A.shape[0]
    res = np.zeros(N)
    for i in prange(N):
        for j in prange(N):
            res = res + A[i, j, :].mean()
    return res / N**2

@njit(parallel=True)
def dist_mat(X):
    """
    Vector X to distance matrix D
    """
    N = len(X)
    D = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            D[i, j] = LA.norm(X[i] - X[j]) # L2
    return D

@njit(parallel=True)
def dist_mat_diff(X):
    """
    Vector X to distance matrix D
    """
    N = X.shape[0]
    P = X.shape[1]
    D_diff = np.zeros((N, N, P))
    for i in range(N):
        for j in range(N):
            diff = X[i] - X[j]
            if (diff == 0).all():
                D_diff[i, j] = diff
            else:
                D_diff[i, j] = diff / LA.norm(X[i] - X[j])
    return D_diff

@njit(parallel=True)
def re_centered_dist(D):
    """
    Distance matrix D to re-centered distance matrix R
    """
    N = D.shape[0] # D should be square NxN, where N is len(X)
    R = np.zeros_like(D)
    c_mean = mean_numba_axis0(D)
    r_mean = mean_numba_axis1(D)
    m_mean = np.mean(D)
    for i in range(N):
        for j in range(N):
            R[i, j] = D[i, j]
            - c_mean[j]
            - r_mean[i]
            + m_mean
    return R

@njit(parallel=True)
def dist_mat_vec(X):
    """
    Vector X to distance matrix D/
    """
    N = len(X)
    D = np.zeros((N, N))
    for i in range(N):
        for j in range(N):
            D[i, j] = X[i] - X[j] # L2
    return D

#@njit(parallel=True)
def re_centered_dist_u(u, X):
    """
    X @ u is vector, not matrix?
    """
    u_X = np.dot(X, u)
    D_u = dist_mat_vec(u_X)
    R_u = re_centered_dist(D_u)
    return  R_u

@njit(parallel=True)
def dist_cov_sq(R_X, R_Y):
    """
    Uses re-centered distance covariance matrices
    """
    v_sum = np.sum(R_X * R_Y)
    N = R_X.shape[0] # R must be square and same length
    return v_sum / N**2

#@njit(parallel=True)
def dist_cov_sq_grad(u, X, R_Y):
    """
    Gradient for use in projected gradient descent optimization
    """
    def delta(X, u, i, j, N):
        sign_term = np.sign((X[i] - X[j]) @ u)
        return np.full(N, ((X[i] - X[j]) * sign_term)[0])
    D_diff = dist_mat_diff(X)
    c_mean = mean_numba_axis0_3d(D_diff)
    r_mean = mean_numba_axis1_3d(D_diff)
    m_mean = mean_numba_m_3d(D_diff)
    N = R_Y.shape[0]
    grad_sum = np.zeros(N)
    for i in range(N):
        for j in range(N):
            grad_sum = grad_sum + R_Y[i, j] * (
                delta(X, u, i, j, N)
                - c_mean[j]
                - r_mean[i]
                + m_mean
            )
    return (1 / N**2) * grad_sum.T

@njit(parallel=True)
def dist_cov_sq_grad_stochastic(u, X, R_Y, sto_sample):
    """
    Gradient for use in projected stochastic gradient descent optimization
    """
    def delta(u, i, j):
        sign_term = np.squeeze(np.sign((X[i] - X[j]) @ u))
        #print(f"X shape: {(X[i] - X[j]).T.shape}")
        #print(f"sign term: {sign_term}")
        return np.dot((X[i] - X[j]).T, sign_term)
    N = R_Y.shape[0]
    grad_sum = 0.
    for j in range(N):
        grad_sum += R_Y[j] * (
            delta(u, sto_sample, j)
            - delta(u, range(N), j)
            - delta(u, sto_sample, range(N))
            + delta(u, range(N), range(N))
        )
    return (1 / N**2) * grad_sum.T

@njit(parallel=True)
def normalize_u(u):
    norm = LA.norm(u)
    return  u / norm

#@njit(parallel=True)
def optim_u_gd(u, X, R_Y, lr, epsilon):
    """
    Gradient ascent for v^2 with respect to u
    TODO: Regularization?
    """
    R_X_u = re_centered_dist_u(u, X)
    v = dist_cov_sq(R_Y, R_X_u)
    u_opt = np.copy(u)
    #iter_ct = 0
    while True:
        #iter_ct += 1
        #print(iter_ct)
        grad = dist_cov_sq_grad(u_opt, X, R_Y)
        u_opt = u_opt + lr * grad # "+=": gradient ascent
        u_opt = normalize_u(u_opt)
        R_X_u_opt = re_centered_dist_u(u_opt, X)
        v_opt = dist_cov_sq(R_Y, R_X_u_opt)
        delta = np.mean(np.square(v_opt - v)) #MSE
        if delta <= epsilon:
            break
        else:
            v = v_opt
    return u_opt, v_opt

@njit(parallel=True)
def optim_u_gd_stochastic(u, X, R_Y, lr, epsilon):
    """
    Stochastic gradient ascent for v^2 with respect to u
    TODO: Regularization?
    """
    sample_ct = X.shape[0]
    R_X_u = re_centered_dist_u(u, X)
    v = dist_cov_sq(R_Y, R_X_u)
    u_opt = np.copy(u)
    while True:
        sto_sample = np.random.randint(0, sample_ct)
        grad = dist_cov_sq_grad_stochastic(u_opt, X, R_Y[sto_sample], sto_sample) # TODO: rewrite this for single sample?
        u_opt += lr * grad # "+=": gradient ascent
        u_opt = normalize_u(u_opt)
        R_X_u_opt = re_centered_dist_u(u_opt, X)
        v_opt = dist_cov_sq(R_Y, R_X_u_opt)
        delta = np.mean(np.square(v_opt - v)) #MSE
        if delta <= epsilon:
            break
        else:
            v = v_opt
    return u_opt, v_opt

@njit(parallel=True)
def k_test(v, v_opt, k, p=.1):
    """
    Test if U[:, k] is significant with respect to U[:, 1:k-1]
    Permutation test not needed for single dataset X
    TODO: Viable for single dataset?
    TODO: Always fails for low k?
    """
    if k == 0:
        return True
    else:
        if sum(v_opt > v[:k]) / k > 1 - p: # k is also len(v[:k])
            return True
        else:
            return False

@njit(parallel=True)
def proj_U(X, U, k):
    """
    Project X onto the orthogonal subspace of k dim of U
    """
    q, _ = LA.qr(U[:, :k])
    #X_proj = np.sum(X * U[:, :k+1].T, axis=1) # vectorized dot
    X_proj = np.zeros_like(X) # looped proj
    for n in range(X_proj.shape[0]):
        for k_i in range(k):
            X_proj[n] = X_proj[n] + (np.dot(X[n], q[:, k_i]) / np.dot(q[:, k_i], q[:, k_i])) * q[:, k_i]
    return X_proj

@njit(parallel=True)
def dca(X, Y, K=None, lr=1e-1, epsilon=1e-5):
    """
    Perform DCA dimensionality reduction on X
    Single dataset X
    K is desired dim for reduction of X
    """
    k = 0
    v = np.zeros(X.shape[1])
    U = np.zeros_like(X.T)
    X_proj = np.copy(X)
    D_Y = dist_mat(Y)
    R_Y = re_centered_dist(D_Y)
    for k in range(0, K):
        u_init = normalize_u(np.random.rand(X.shape[1]))
        u_opt, v_opt = optim_u_gd(u_init, X_proj, R_Y, lr, epsilon)
        if K is not None or k_test(v, v_opt, k):
            U[:, k] = u_opt
            v[k] = v_opt
            X_proj = proj_U(X_proj, U, k+1) # then inc k, unnecessary if this is last k
        else:
            break
    return U[:, :k+1], v[:k+1]
