// // var test = Math.random()*10;
// // console.log("question a: " +test);

// // // var ceil = Math.ceil(2.49);
// // // console.log(ceil);

// // let decimal = Math.random() * 10;
// // let rounded = Math.ceil(decimal);
// // console.log("question 4: " + rounded);

// // var opt1 = Math.floor(Math.random() * 10);
// // var opt2 = Math.random()*Math.ceil(10);
// // var opt3 = Math.ceil(Math.random());
// // var opt4 = Math.ceil(Math.random()*10);

// // console.log(opt1 + " Opt1");
// // console.log(opt2 + " Opt2");
// // console.log(opt3 + " Opt3");
// // console.log(opt4 + " Opt4");

// // // QUIZ 
// // var result = "Hello".indexOf("l");
// // console.log("question 5: " + result);


// //   var clothes = [];
// //   clothes.push('gray t-shirt');
// //   clothes.push('green scarf');
// //   clothes.pop();
// //   clothes.push('slippers');
// //   clothes.pop();
// //   clothes.push('boots');
// //   clothes.push('old jeans');
// //   console.log("question 6: " + clothes.length);

// //    var food = [];
// //   food.push('Chocolate');
// //   food.push('Ice cream');
// //   food.push('Donut');
// //   console.log("question 7: " + food[1]);

// //     var dog = {
// //       color: "brown",
// //       height: 30,
// //       length: 60
// //   };
// //   dog["type"] = "corgi";
// //     console.log("question 8: " + dog);
// //     console.log(dog)

// var result = null;
// console.log(result);

// try {
//   console.log('hi');
// } catch (err){
//   console.log('bye');
// }

// var x;
// if (x === null){
//   console.log('x is null');
// } else if (x === undefined){
//   console.log('x is undefined');
// } else{
//   console.log('x is defined');
// }

// // throw new Error('This is an error');
// // console.log('This will not be executed');

// var bicycle = {
//   wheels: 2,
//   start: function() {
//     console.log('Starting the bicycle...');
//   },
//   stop: function() {
//     console.log('Stopping the bicycle...');
//   }
// };
// console.log(bicycle);

// try{
//   throw new Error('This is an error');
//   console.log('hi');
// } catch (err) {
//   console.log('bye');
// }

// function add(a, b) {
//   summ = a + b;
//   console.log(summ);
// }
// add(3, "10");
// console.log(typeof(summ));

// var str = "Hello";
// console.log(str.match("jello"));

// try{
//   Number(5).toPrecision(300);
// } catch (e) {
//   console.log("There was an error");
// }



// Fibonacci sequence is a series of numbers where each number is the sum of the two preceding ones, usually starting with 0 and 1. The sequence goes: 0, 1, 1, 2, 3, 5, 8, 13, 21, and so on.

function generate_fibonacci(n) {
  // Generates the first 'n' numbers of the Fibonacci sequence.
  if (n <= 0) {
    return [];
  } else if (n === 1) {
    return [0];
  }
  var sequence = [0, 1];
  for (var i = 2; i < n; i++) {
    // Add the last two numbers in the list together
    var nextNumber = sequence[i - 1] + sequence[i - 2];
    sequence.push(nextNumber);
  }
  return sequence;
}

console.log(generate_fibonacci(20));  

function fibonacci(n) {
    if (n === 0) {
        return 0;
    } 

    if (n === 1 || n === 2) {
        return 1;  
    } 

    return fibonacci(n - 1) + fibonacci(n - 2);
}

console.log(fibonacci(20));
