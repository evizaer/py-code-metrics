"""Module c — imports a (closes cycle)."""

from . import a


def marker():
    return a.shared_double(1)


class Animal:
    def speak(self):
        return "..."


class Dog(Animal):
    def speak(self):
        return "woof"


class Cat(Animal):
    def speak(self):
        return "meow"


def chorus(animal: Animal):
    # Polymorphic call site — v_poly should expand speak targets
    return animal.speak()


class Split:
    def use_a(self):
        return self.a

    def set_a(self, v):
        self.a = v

    def use_b(self):
        return self.b

    def set_b(self, v):
        self.b = v
