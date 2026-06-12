import cli
import os

fn main() {
	app := cli.new_app()
	exit(app.run())
}
