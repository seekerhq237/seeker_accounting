"""Patch test to use ALL_RETURN_STATUS_CODES_EXTENDED."""


def main() -> None:
	path = "tests/test_slice_t47_vat_state_machine.py"
	content = open(path, "rb").read()

	old = b"            ALL_RETURN_STATUS_CODES,\r\n"
	new = b"            ALL_RETURN_STATUS_CODES_EXTENDED,\r\n"
	assert old in content, "Pattern 1 not found"
	content = content.replace(old, new, 1)

	old2 = b"ALL_RETURN_STATUS_CODES)\r\n"
	new2 = b"ALL_RETURN_STATUS_CODES_EXTENDED)\r\n"
	content = content.replace(old2, new2)

	open(path, "wb").write(content)
	print("Done")


if __name__ == "__main__":
	main()
