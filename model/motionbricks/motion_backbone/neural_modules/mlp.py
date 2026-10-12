import torch as t


class FCBlock(t.nn.Module):
    """Fully connected residual block"""

    def __init__(self, num_layers: int, layer_width: int, size_in: int, size_out: int, dropout: float = 0.0):
        super().__init__()
        self.num_layers = num_layers
        self.layer_width = layer_width

        fc_layers: list[t.nn.Module] = [t.nn.Linear(size_in, layer_width)]
        relu_layers: list[t.nn.Module] = [t.nn.LeakyReLU(inplace=True)]
        if dropout > 0.0:
            fc_layers.append(t.nn.Dropout(p=dropout))
            relu_layers.append(t.nn.Identity())
        fc_layers += [t.nn.Linear(layer_width, layer_width) for _ in range(num_layers - 1)]
        relu_layers += [t.nn.LeakyReLU(inplace=True) for _ in range(num_layers - 1)]

        self.forward_projection = t.nn.Linear(layer_width, size_out)
        self.fc_layers = t.nn.ModuleList(fc_layers)
        self.relu_layers = t.nn.ModuleList(relu_layers)

    def forward(self, x: t.Tensor):
        h = x
        for layer, relu in zip(self.fc_layers, self.relu_layers):
            h = relu(layer(h))
        f = self.forward_projection(h)
        return f
