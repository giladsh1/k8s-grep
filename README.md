# k8s-grep


k8s-grep is a tool that lets you filter specific resources from a stream of Kubernetes YAML manifests, produced by tools such as [Kustomize](https://github.com/kubernetes-sigs/kustomize).


## Example usage:
```
usage: k8s-grep [options]

optional arguments:
-h, --help            show this help message and exit
  -n NAME, --name NAME  filter by name - can be passed multiple times
  -k KIND, --kind KIND  filter by kind - can be passed multiple times
  -d DIRECTORY, --directory DIRECTORY
                        directory path to build
  -xn XNAME, --exclude-name XNAME
                        exclude by name - can be passed multiple times
  -xk XKIND, --exclude-kind XKIND
                        exclude by kind - can be passed multiple times
```

### Examples:
`./k8s-grep --directory dev --name gateway` - will output all objects with the name `gateway`.

`./k8s-grep --directory dev --name gateway --name web` - will output all objects with the name `gateway` or `web`.

`./k8s-grep --directory dev --name gateway --kind service` - will output all objects with the name `gateway` and kind `service`.

`./k8s-grep --directory dev --exclude-name mobile` - will output all objects with the NOT named `mobile`.

You can pipe the output into kubectl: `./k8s-grep --directory dev --name console | kubectl diff -f -`

## Installation
```
python3 -m pip install pyyaml # ensure Python YAML module is installed
git clone https://github.com/giladsh1/k8s-grep.git
sudo ln -s $(pwd)/k8s-grep/k8s-grep /usr/local/bin/k8s-grep
```
