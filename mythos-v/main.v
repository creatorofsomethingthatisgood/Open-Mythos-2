import cli
import os
import cli.app

fn main() {
	app := cli.new_app()
	exit(app.run())
}
