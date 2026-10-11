{
  description = "Negative Lab Basic: invert phone photos of B&W film negatives";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        runtimeDeps = ps: with ps; [
          numpy
          opencv4
          pillow
          pillow-heif
          rawpy
        ];

        nlb = python.pkgs.buildPythonApplication {
          pname = "nlb";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          build-system = [ python.pkgs.hatchling ];
          dependencies = runtimeDeps python.pkgs;

          # nixpkgs ships cv2 as `opencv4`, not the `opencv-python-headless` wheel.
          pythonRemoveDeps = [ "opencv-python-headless" ];

          nativeCheckInputs = with python.pkgs; [ pytestCheckHook tifffile ];
          pythonImportsCheck = [ "nlb" ];
        };
      in
      {
        packages.default = nlb;

        apps.default = flake-utils.lib.mkApp { drv = nlb; };

        devShells.default = pkgs.mkShell {
          packages = [
            (python.withPackages (ps: runtimeDeps ps ++ (with ps; [ pytest tifffile ])))
          ];
          shellHook = ''
            export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
          '';
        };
      });
}
